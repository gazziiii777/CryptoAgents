import asyncio
import logging

from app.adapters.clients.binance.client import BinanceClient
from app.adapters.clients.binance.models import OISnapshot
from app.adapters.clients.ccxt.client import CcxtClient
from app.adapters.clients.ccxt.models import OHLCVCandle
from app.adapters.clients.coinglass.client import CoinGlassClient
from app.adapters.clients.coinglass.exceptions import CoinGlassAPIError, CoinGlassAuthError
from app.services.liquidity.builder import build_liquidity_map
from app.domain.models.liquidity import LiquidityMap
from app.services.screener.criteria import (
    classify_smart_money_divergence,
    compute_direction,
    compute_score,
)
from app.domain.indicators import (
    calc_adx,
    calc_aggregated_oi_trend,
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
    calc_positioning_regime,
    calc_rsi_divergence,
    calc_rsi_level,
    calc_spot_perp_divergence,
    calc_squeeze_setup,
    calc_volume_spike,
    calc_vwap_bias,
)
from app.domain.models.screener import ScreenerResult, SignalDetails, empty_signals
from core.settings import settings

logger = logging.getLogger(__name__)


def _calc_oi_change_4h(oi_hist: list[OISnapshot]) -> float:
    if len(oi_hist) < 2:
        return 0.0
    prev_oi = oi_hist[-2].open_interest
    curr_oi = oi_hist[-1].open_interest
    if prev_oi == 0:
        return 0.0
    return (curr_oi - prev_oi) / prev_oi


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
        cg_client.fetch_futures_basis_history(
            symbol, limit=settings.SCREENER_BASIS_LIMIT
        ),
        binance_client.fetch_spot_cvd(symbol, num_candles=settings.CVD_CANDLES),
        cg_client.fetch_oi_aggregated_history(symbol, limit=settings.OI_HISTORY_LIMIT),
        return_exceptions=True,
    )
    cg_names = ("liquidation", "top_position_ratio", "oi_funding", "basis")
    for name, result in zip(cg_names, cg_raw):
        if isinstance(result, CoinGlassAuthError):
            raise result
        if isinstance(result, CoinGlassAPIError):
            logger.debug(
                "evaluate_symbol: CoinGlass %s no data for %s: %s", name, symbol, result
            )
        elif isinstance(result, Exception):
            logger.warning(
                "evaluate_symbol: CoinGlass %s failed for %s: %s", name, symbol, result
            )
    liq_history = cg_raw[0] if not isinstance(cg_raw[0], BaseException) else []
    top_ratio_hist = cg_raw[1] if not isinstance(cg_raw[1], BaseException) else []
    oi_weighted_funding_hist = (
        cg_raw[2] if not isinstance(cg_raw[2], BaseException) else []
    )
    basis_hist = cg_raw[3] if not isinstance(cg_raw[3], BaseException) else []
    spot_cvd = cg_raw[4] if not isinstance(cg_raw[4], BaseException) else []
    oi_aggregated_hist = cg_raw[5] if not isinstance(cg_raw[5], BaseException) else []

    retail_ls = ls_hist[-1].long_short_ratio if ls_hist else None
    top_ls = top_ratio_hist[-1].long_short_ratio if top_ratio_hist else None

    funding_bias = calc_funding_bias(funding_hist)
    oi_weighted_funding_bias = calc_oi_weighted_funding_bias(oi_weighted_funding_hist)
    positioning_regime = calc_positioning_regime(candles_4h, oi_hist)
    effective_funding_bias = (
        oi_weighted_funding_bias
        if oi_weighted_funding_bias != "neutral"
        else funding_bias
    )
    squeeze_setup = calc_squeeze_setup(positioning_regime, effective_funding_bias)
    spot_perp_divergence = calc_spot_perp_divergence(spot_cvd, cvd)

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
        oi_aggregated_trend=calc_aggregated_oi_trend(oi_aggregated_hist),
        funding_rate=funding_hist[-1].funding_rate if funding_hist else 0.0,
        funding_bias=funding_bias,
        oi_weighted_funding_bias=oi_weighted_funding_bias,
        long_short_ratio=retail_ls,
        cvd_trend=calc_cvd_trend(cvd),
        cvd_price_divergence=calc_cvd_price_divergence(candles_4h, cvd),
        liq_spike=calc_liquidation_spike(liq_history),
        top_trader_ls_ratio=top_ls,
        basis=basis_hist[-1].close_basis if basis_hist else None,
        smart_money_divergence=classify_smart_money_divergence(
            retail_ls, top_ls, settings.LS_RATIO_HIGH, settings.LS_RATIO_LOW
        ),
        positioning_regime=positioning_regime,
        squeeze_setup=squeeze_setup,
        spot_perp_divergence=spot_perp_divergence,
    )

    score = compute_score(signals)
    direction = compute_direction(signals)
    logger.info(
        "evaluate_symbol: %s score=%d adx=%.1f direction=%s regime=%s squeeze=%s spot_perp=%s",
        symbol,
        score,
        adx,
        direction,
        positioning_regime,
        squeeze_setup,
        spot_perp_divergence,
    )

    liquidity_map = await _build_liquidity(symbol, ccxt_client, candles_4h)

    return ScreenerResult(
        symbol=symbol,
        gate_passed=True,
        score=score,
        adx=adx,
        direction=direction,
        signals=signals,
        liquidity_map=liquidity_map,
    )


async def _build_liquidity(
    symbol: str, ccxt_client: CcxtClient, candles_4h: list[OHLCVCandle]
) -> LiquidityMap:
    """Считает карту ликвидности (observe-only): стакан нефатально, кластеры из свечей.

    Сбой фетча стакана не валит оценку символа — карта строится без стен.
    """
    if not candles_4h:
        return build_liquidity_map(
            symbol=symbol, mark_price=0.0, candles=[], order_book=None
        )
    order_book = None
    try:
        order_book = await ccxt_client.fetch_order_book(symbol)
    except Exception:
        logger.warning(
            "evaluate_symbol: order book fetch failed for %s", symbol, exc_info=True
        )
    liquidity_map = build_liquidity_map(
        symbol=symbol,
        mark_price=candles_4h[-1].close,
        candles=candles_4h,
        order_book=order_book,
    )
    magnet_above = liquidity_map.nearest_magnet_above
    magnet_below = liquidity_map.nearest_magnet_below
    logger.info(
        "liquidity: %s mark=%.6g walls=%d clusters=%d imbalance=%.2f"
        " magnet_above=%s magnet_below=%s",
        symbol,
        liquidity_map.mark_price,
        len(liquidity_map.walls),
        len(liquidity_map.liq_clusters),
        liquidity_map.book_imbalance,
        f"{magnet_above.price:.6g}" if magnet_above else "none",
        f"{magnet_below.price:.6g}" if magnet_below else "none",
    )
    return liquidity_map
