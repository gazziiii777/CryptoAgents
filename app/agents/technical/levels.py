import pandas as pd

from app.agents.technical.models import TechnicalFacts
from app.clients.ccxt.models import OHLCVCandle
from app.screener.indicators import (
    calc_adx,
    calc_atr,
    calc_daily_trend,
    calc_ema_cross,
    calc_macd,
    calc_rsi_divergence,
    calc_rsi_level,
)

_RECENT_LOOKBACK_4H = 30
_EMA_FAST = 20
_EMA_SLOW = 50


def _ema(closes: list[float], span: int) -> float:
    return float(pd.Series(closes).ewm(span=span, adjust=False).mean().iloc[-1])


def compute_facts(
    candles_4h: list[OHLCVCandle], candles_1d: list[OHLCVCandle]
) -> TechnicalFacts:
    """Считает уровни из свечей 4h/1d детерминированно (без LLM)."""
    if not candles_4h or not candles_1d:
        raise ValueError("compute_facts requires non-empty 4h and 1d candle series")
    closes = [c.close for c in candles_4h]
    recent = candles_4h[-_RECENT_LOOKBACK_4H:]
    prev_day = candles_1d[-2] if len(candles_1d) >= 2 else candles_1d[-1]
    return TechnicalFacts(
        current_price=closes[-1],
        atr=calc_atr(candles_4h),
        ema_20=_ema(closes, _EMA_FAST),
        ema_50=_ema(closes, _EMA_SLOW),
        recent_high=max(c.high for c in recent),
        recent_low=min(c.low for c in recent),
        prev_day_high=prev_day.high,
        prev_day_low=prev_day.low,
        adx=calc_adx(candles_4h),
        rsi=calc_rsi_level(candles_4h),
        rsi_divergence=calc_rsi_divergence(candles_4h),
        macd=calc_macd(candles_4h),
        ema_cross=calc_ema_cross(candles_4h),
        daily_trend=calc_daily_trend(candles_1d),
    )
