from __future__ import annotations

import asyncio
import logging

from pydantic import BaseModel, ConfigDict

from app.clients.binance.client import BinanceClient
from app.clients.binance.models import OISnapshot
from app.clients.ccxt.client import CcxtClient
from app.clients.coinglass.client import CoinGlassAuthError, CoinGlassClient
from core import settings
from app.screener.indicators import (
    calc_adx,
    calc_atr,
    calc_bb_squeeze,
    calc_cvd_price_divergence,
    calc_cvd_trend,
    calc_daily_trend,
    calc_ema_cross,
    calc_funding_bias,
    calc_liquidation_spike,
    calc_macd,
    calc_near_swing,
    calc_oi_trend,
    calc_oi_weighted_funding_bias,
    calc_rsi_divergence,
    calc_rsi_level,
    calc_volume_spike,
    calc_vwap_bias,
)

logger = logging.getLogger(__name__)

_FROZEN = ConfigDict(frozen=True, extra="ignore")


class SignalDetails(BaseModel):
    model_config = _FROZEN

    atr: float
    volume_spike: bool
    bb_squeeze: bool
    ema_cross: str | None
    rsi_level: float | None
    rsi_divergence: str | None
    macd: str | None
    vwap_bias: str
    daily_trend: str
    near_swing: bool
    oi_change_4h_pct: float
    oi_trend: str
    funding_rate: float
    funding_bias: str
    oi_weighted_funding_bias: str
    long_short_ratio: float | None
    cvd_trend: str
    cvd_price_divergence: str | None
    liq_spike: bool
    top_trader_ls_ratio: float | None
    basis: float | None


class ScreenerResult(BaseModel):
    model_config = _FROZEN

    symbol: str
    gate_passed: bool
    score: int
    adx: float
    direction: str
    signals: SignalDetails


def _calc_oi_change_4h(oi_hist: list[OISnapshot]) -> float:
    if len(oi_hist) < 2:
        return 0.0
    prev_oi = oi_hist[-2].open_interest
    curr_oi = oi_hist[-1].open_interest
    if prev_oi == 0:
        return 0.0
    return (curr_oi - prev_oi) / prev_oi


def _compute_direction(sig: SignalDetails) -> str:
    """Голосование по направленным сигналам: 'long', 'short' или 'mixed'.

    Порог ±DIRECTION_VOTE_THRESHOLD: минимум столько перевесов в одну сторону.
    Контрарные сигналы (retail L/S, funding, OI-weighted funding, basis) инвертированы.
    """
    votes = 0

    if sig.ema_cross == "golden":
        votes += 1
    elif sig.ema_cross == "death":
        votes -= 1

    if sig.rsi_divergence == "bullish":
        votes += 1
    elif sig.rsi_divergence == "bearish":
        votes -= 1

    if sig.macd == "bullish":
        votes += 1
    elif sig.macd == "bearish":
        votes -= 1

    if sig.cvd_price_divergence == "bullish":
        votes += 1
    elif sig.cvd_price_divergence == "bearish":
        votes -= 1

    if sig.daily_trend == "up":
        votes += 1
    elif sig.daily_trend == "down":
        votes -= 1

    if sig.vwap_bias == "above":
        votes += 1
    elif sig.vwap_bias == "below":
        votes -= 1

    if sig.cvd_trend == "rising":
        votes += 1
    elif sig.cvd_trend == "falling":
        votes -= 1

    ls = sig.long_short_ratio
    if ls is not None:
        if ls >= settings.LS_RATIO_HIGH:
            votes -= 1
        elif ls <= settings.LS_RATIO_LOW:
            votes += 1

    top_ls = sig.top_trader_ls_ratio
    if top_ls is not None:
        if top_ls >= settings.LS_RATIO_HIGH:
            votes += 1
        elif top_ls <= settings.LS_RATIO_LOW:
            votes -= 1

    funding = (
        sig.oi_weighted_funding_bias
        if sig.oi_weighted_funding_bias != "neutral"
        else sig.funding_bias
    )
    if funding == "long_heavy":
        votes -= 1
    elif funding == "short_heavy":
        votes += 1

    basis = sig.basis
    if basis is not None:
        if basis >= settings.BASIS_CONTANGO_THRESHOLD:
            votes += 1
        elif basis <= -settings.BASIS_CONTANGO_THRESHOLD:
            votes -= 1

    if votes >= settings.DIRECTION_VOTE_THRESHOLD:
        return "long"
    if votes <= -settings.DIRECTION_VOTE_THRESHOLD:
        return "short"
    return "mixed"


def _compute_score(sig: SignalDetails) -> int:
    score = 0

    if sig.volume_spike:
        score += 1
    if sig.bb_squeeze:
        score += 1
    if sig.near_swing:
        score += 1

    if sig.ema_cross is not None:
        score += 1
    if sig.rsi_divergence is not None:
        score += 1
    if sig.macd is not None:
        score += 1
    if sig.cvd_price_divergence is not None:
        score += 1

    rsi = sig.rsi_level
    if rsi is not None and (
        rsi >= settings.RSI_OVERBOUGHT or rsi <= settings.RSI_OVERSOLD
    ):
        score += 1

    ls = sig.long_short_ratio
    if ls is not None and (ls >= settings.LS_RATIO_HIGH or ls <= settings.LS_RATIO_LOW):
        score += 1

    top_ls = sig.top_trader_ls_ratio
    if top_ls is not None and (
        top_ls >= settings.LS_RATIO_HIGH or top_ls <= settings.LS_RATIO_LOW
    ):
        score += 1

    if (sig.daily_trend == "up" and sig.vwap_bias == "above") or (
        sig.daily_trend == "down" and sig.vwap_bias == "below"
    ):
        score += 1

    if sig.funding_bias != "neutral" or sig.oi_weighted_funding_bias != "neutral":
        score += 1
    if sig.oi_trend != "neutral":
        score += 1

    if abs(sig.oi_change_4h_pct) >= settings.OI_CHANGE_4H_SCORE_PCT:
        score += 1

    if sig.liq_spike:
        score += 1

    return score


def empty_signals() -> SignalDetails:
    return SignalDetails(
        atr=0.0,
        volume_spike=False,
        bb_squeeze=False,
        ema_cross=None,
        rsi_level=None,
        rsi_divergence=None,
        macd=None,
        vwap_bias="unknown",
        daily_trend="neutral",
        near_swing=False,
        oi_change_4h_pct=0.0,
        oi_trend="neutral",
        funding_rate=0.0,
        funding_bias="neutral",
        oi_weighted_funding_bias="neutral",
        long_short_ratio=None,
        cvd_trend="neutral",
        cvd_price_divergence=None,
        liq_spike=False,
        top_trader_ls_ratio=None,
        basis=None,
    )


def _failed_result(symbol: str) -> ScreenerResult:
    return ScreenerResult(
        symbol=symbol,
        gate_passed=False,
        score=0,
        adx=0.0,
        direction="mixed",
        signals=empty_signals(),
    )


async def evaluate_symbol(
    symbol: str,
    ccxt_client: CcxtClient,
    binance_client: BinanceClient,
    cg_client: CoinGlassClient,
) -> ScreenerResult:
    """Оценить один символ для скринера.

    Шаги: параллельный фетч данных → ADX gate → расчёт всех сигналов → score + direction.
    При ошибке фетча возвращает gate_passed=False без исключения — не ломает параллельный скринер.
    CoinGlass фетч не блокирует: при ошибке CG-сигналы остаются пустыми.
    """
    try:
        (
            candles_4h,
            candles_1d,
            funding_hist,
            oi_hist,
            ls_hist,
            cvd,
        ) = await asyncio.gather(
            ccxt_client.fetch_ohlcv(
                symbol, timeframe="4h", limit=settings.SCREENER_4H_LIMIT
            ),
            ccxt_client.fetch_ohlcv(
                symbol, timeframe="1d", limit=settings.SCREENER_1D_LIMIT
            ),
            ccxt_client.fetch_funding_rate_history(
                symbol, limit=settings.FUNDING_HISTORY_LIMIT
            ),
            binance_client.fetch_open_interest_history(
                symbol, period="4h", limit=settings.OI_HISTORY_LIMIT
            ),
            binance_client.fetch_long_short_ratio(
                symbol, period="4h", limit=settings.SCREENER_LS_RATIO_LIMIT
            ),
            binance_client.fetch_cvd(symbol, num_candles=settings.CVD_CANDLES),
        )
    except Exception:
        logger.error("evaluate_symbol: data fetch failed for %s", symbol, exc_info=True)
        return _failed_result(symbol)

    adx = calc_adx(candles_4h)
    if adx < settings.ADX_GATE_MIN:
        logger.debug("evaluate_symbol: %s filtered by ADX gate (adx=%.1f)", symbol, adx)
        return ScreenerResult(
            symbol=symbol,
            gate_passed=False,
            score=0,
            adx=adx,
            direction="mixed",
            signals=empty_signals(),
        )

    cg_raw = await asyncio.gather(
        cg_client.fetch_liquidation_aggregated_history(symbol),
        cg_client.fetch_top_position_ratio(
            symbol, limit=settings.SCREENER_LS_RATIO_LIMIT
        ),
        cg_client.fetch_funding_rate_oi_weight_history(
            symbol, limit=settings.FUNDING_HISTORY_LIMIT
        ),
        cg_client.fetch_futures_basis_history(symbol, limit=1),
        return_exceptions=True,
    )
    cg_names = ("liquidation", "top_position_ratio", "oi_funding", "basis")
    for name, result in zip(cg_names, cg_raw):
        if isinstance(result, CoinGlassAuthError):
            raise result
        if isinstance(result, Exception):
            logger.warning(
                "evaluate_symbol: CoinGlass %s failed for %s: %s", name, symbol, result
            )
    liq_history = cg_raw[0] if not isinstance(cg_raw[0], Exception) else []
    top_ratio_hist = cg_raw[1] if not isinstance(cg_raw[1], Exception) else []
    oi_weighted_funding_hist = cg_raw[2] if not isinstance(cg_raw[2], Exception) else []
    basis_hist = cg_raw[3] if not isinstance(cg_raw[3], Exception) else []

    signals = SignalDetails(
        atr=calc_atr(candles_4h),
        volume_spike=calc_volume_spike(candles_4h),
        bb_squeeze=calc_bb_squeeze(candles_4h),
        ema_cross=calc_ema_cross(candles_4h),
        rsi_level=calc_rsi_level(candles_4h),
        rsi_divergence=calc_rsi_divergence(candles_4h),
        macd=calc_macd(candles_4h),
        vwap_bias=calc_vwap_bias(candles_4h),
        daily_trend=calc_daily_trend(candles_1d),
        near_swing=calc_near_swing(candles_1d, window=settings.NEAR_SWING_WINDOW),
        oi_change_4h_pct=_calc_oi_change_4h(oi_hist),
        oi_trend=calc_oi_trend(oi_hist),
        funding_rate=funding_hist[-1].funding_rate if funding_hist else 0.0,
        funding_bias=calc_funding_bias(funding_hist),
        oi_weighted_funding_bias=calc_oi_weighted_funding_bias(
            oi_weighted_funding_hist
        ),
        long_short_ratio=ls_hist[-1].long_short_ratio if ls_hist else None,
        cvd_trend=calc_cvd_trend(cvd),
        cvd_price_divergence=calc_cvd_price_divergence(candles_4h, cvd),
        liq_spike=calc_liquidation_spike(liq_history),
        top_trader_ls_ratio=(
            top_ratio_hist[-1].long_short_ratio if top_ratio_hist else None
        ),
        basis=basis_hist[-1].close_basis if basis_hist else None,
    )

    score = _compute_score(signals)
    direction = _compute_direction(signals)
    logger.info(
        "evaluate_symbol: %s score=%d adx=%.1f direction=%s",
        symbol,
        score,
        adx,
        direction,
    )

    return ScreenerResult(
        symbol=symbol,
        gate_passed=True,
        score=score,
        adx=adx,
        direction=direction,
        signals=signals,
    )
