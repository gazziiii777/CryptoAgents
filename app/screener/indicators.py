from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import ta

from app.clients.binance.models import CVDPoint, OISnapshot
from app.clients.ccxt.models import FundingRateHistoryEntry, OHLCVCandle
from app.clients.coinglass.models import FundingRateOHLC, LiquidationHistoryPoint
from core import settings

logger = logging.getLogger(__name__)


def _to_df(candles: list[OHLCVCandle]) -> pd.DataFrame:
    return pd.DataFrame([c.model_dump() for c in candles]).set_index("timestamp")


def _local_minima(values: list[float], radius: int = 2) -> list[tuple[int, float]]:
    """Индексы и значения локальных минимумов: точка меньше radius соседей с каждой стороны."""
    result = []
    for i in range(radius, len(values) - radius):
        window = values[i - radius : i] + values[i + 1 : i + radius + 1]
        if values[i] < min(window):
            result.append((i, values[i]))
    return result


def _local_maxima(values: list[float], radius: int = 2) -> list[tuple[int, float]]:
    """Индексы и значения локальных максимумов: точка больше radius соседей с каждой стороны."""
    result = []
    for i in range(radius, len(values) - radius):
        window = values[i - radius : i] + values[i + 1 : i + radius + 1]
        if values[i] > max(window):
            result.append((i, values[i]))
    return result


def calc_adx(candles: list[OHLCVCandle], period: int = 14) -> float:
    """ADX последней свечи. Минимум period*3 свечей для надёжности, иначе 0.0."""
    if len(candles) < period * 3:
        logger.warning("ADX: insufficient candles (%d < %d)", len(candles), period * 3)
        return 0.0

    df = _to_df(candles)
    adx = ta.trend.ADXIndicator(
        high=df["high"], low=df["low"], close=df["close"], window=period
    )
    value = adx.adx().iloc[-1]
    return float(value) if not np.isnan(value) else 0.0


def calc_atr(candles: list[OHLCVCandle], period: int = 14) -> float:
    """ATR последней свечи для оценки волатильности и расчёта стопов. 0.0 при нехватке данных."""
    if len(candles) < period + 1:
        return 0.0

    df = _to_df(candles)
    atr = ta.volatility.AverageTrueRange(
        high=df["high"], low=df["low"], close=df["close"], window=period
    )
    value = atr.average_true_range().iloc[-1]
    return float(value) if not np.isnan(value) else 0.0


def calc_rsi_level(candles: list[OHLCVCandle], period: int = 14) -> float | None:
    """RSI последней свечи. None при нехватке данных."""
    if len(candles) < period + 1:
        return None

    df = _to_df(candles)
    rsi = ta.momentum.RSIIndicator(df["close"], window=period).rsi()
    value = rsi.iloc[-1]
    return float(value) if not np.isnan(value) else None


def calc_rsi_divergence(
    candles: list[OHLCVCandle], rsi_period: int = 14, lookback: int = 20
) -> str | None:
    """RSI-дивергенция на последних lookback свечах через локальные экстремумы.

    Бычья: последний локальный low цены ниже предыдущего, RSI — выше.
    Медвежья: последний локальный high цены выше предыдущего, RSI — ниже.
    Возвращает "bullish", "bearish" или None.
    """
    if len(candles) < rsi_period + lookback:
        return None

    df = _to_df(candles)
    rsi_series = ta.momentum.RSIIndicator(df["close"], window=rsi_period).rsi()

    lows = df["low"].iloc[-lookback:].tolist()
    highs = df["high"].iloc[-lookback:].tolist()
    rsi_vals = rsi_series.iloc[-lookback:].tolist()

    price_lows = _local_minima(lows)
    price_highs = _local_maxima(highs)

    if len(price_lows) >= 2:
        (i1, p1), (i2, p2) = price_lows[-2], price_lows[-1]
        r1, r2 = rsi_vals[i1], rsi_vals[i2]
        if not (np.isnan(r1) or np.isnan(r2)):
            if p2 < p1 and r2 > r1:
                return "bullish"

    if len(price_highs) >= 2:
        (i1, p1), (i2, p2) = price_highs[-2], price_highs[-1]
        r1, r2 = rsi_vals[i1], rsi_vals[i2]
        if not (np.isnan(r1) or np.isnan(r2)):
            if p2 > p1 and r2 < r1:
                return "bearish"

    return None


def calc_macd(candles: list[OHLCVCandle]) -> str | None:
    """MACD(12,26,9): 'bullish' — гистограмма > 0 и растёт; 'bearish' — < 0 и падает; None иначе."""
    if len(candles) < 26 * 3:
        return None

    df = _to_df(candles)
    macd_ind = ta.trend.MACD(df["close"], window_slow=26, window_fast=12, window_sign=9)
    hist = macd_ind.macd_diff()

    last = hist.iloc[-1]
    prev = hist.iloc[-2]

    if np.isnan(last) or np.isnan(prev):
        return None

    if last > 0 and last > prev:
        return "bullish"
    if last < 0 and last < prev:
        return "bearish"

    return None


def calc_volume_spike(candles: list[OHLCVCandle], sma_period: int = 20) -> bool:
    """True если volume_last > VOLUME_SPIKE_MULTIPLIER × SMA(sma_period)."""
    if len(candles) < sma_period + 1:
        return False

    volumes = [c.volume for c in candles]
    sma_vol = np.mean(volumes[-(sma_period + 1) : -1])
    return volumes[-1] > settings.VOLUME_SPIKE_MULTIPLIER * sma_vol


def calc_bb_squeeze(
    candles: list[OHLCVCandle], window: int = 20, std_dev: float = 2.0
) -> bool:
    """True если (BB_upper - BB_lower) / BB_mid < BB_SQUEEZE_THRESHOLD (ожидается пробой)."""
    if len(candles) < window + 1:
        return False

    df = _to_df(candles)
    bb = ta.volatility.BollingerBands(df["close"], window=window, window_dev=std_dev)
    upper = bb.bollinger_hband().iloc[-1]
    lower = bb.bollinger_lband().iloc[-1]
    mid = bb.bollinger_mavg().iloc[-1]

    if np.isnan(upper) or np.isnan(lower) or mid == 0:
        return False

    return (upper - lower) / mid < settings.BB_SQUEEZE_THRESHOLD


def calc_ema_cross(
    candles: list[OHLCVCandle], fast: int = 20, slow: int = 50
) -> str | None:
    """ "golden" — fast пересекла slow снизу вверх; "death" — сверху вниз; None — нет пересечения или мало данных."""
    if len(candles) < slow * 3:
        logger.warning(
            "EMA cross: only %d candles (need %d for reliable EMA%d), skipping",
            len(candles),
            slow * 3,
            slow,
        )
        return None

    df = _to_df(candles)
    ema_fast = ta.trend.EMAIndicator(df["close"], window=fast).ema_indicator()
    ema_slow = ta.trend.EMAIndicator(df["close"], window=slow).ema_indicator()

    prev_diff = ema_fast.iloc[-2] - ema_slow.iloc[-2]
    curr_diff = ema_fast.iloc[-1] - ema_slow.iloc[-1]

    if np.isnan(prev_diff) or np.isnan(curr_diff):
        return None

    if prev_diff < 0 and curr_diff >= 0:
        return "golden"
    if prev_diff > 0 and curr_diff <= 0:
        return "death"

    return None


def calc_vwap_bias(candles: list[OHLCVCandle]) -> str:
    """Положение close относительно дневного VWAP (сброс в полночь UTC).

    Если сегодня менее 3 свечей — fallback на последние 12 (48h).
    """
    df = _to_df(candles)
    dt_index = pd.to_datetime(df.index, unit="ms", utc=True)

    today_midnight = dt_index[-1].normalize()
    day_df = df[dt_index >= today_midnight]

    if len(day_df) < 3:
        day_df = df.iloc[-12:]

    typical_price = (day_df["high"] + day_df["low"] + day_df["close"]) / 3
    cumulative_tp_vol = (typical_price * day_df["volume"]).cumsum()
    cumulative_vol = day_df["volume"].cumsum()
    vwap = cumulative_tp_vol / cumulative_vol

    last_close = float(day_df["close"].iloc[-1])
    last_vwap = float(vwap.iloc[-1])

    return "above" if last_close > last_vwap else "below"


def calc_near_swing(candles: list[OHLCVCandle], window: int = 20) -> bool:
    """True если close в пределах NEAR_SWING_ATR_MULT × ATR от swing high/low последних window свечей.

    Порог масштабируется с волатильностью монеты. Для значимых уровней передавать 1D свечи с window=50.
    """
    if len(candles) < window:
        return False

    atr = calc_atr(candles)
    if atr == 0.0:
        return False

    threshold = atr * settings.NEAR_SWING_ATR_MULT
    window_candles = candles[-window:]
    highs = [c.high for c in window_candles]
    lows = [c.low for c in window_candles]
    last_close = candles[-1].close

    swing_high = max(highs)
    swing_low = min(lows)

    return (
        abs(last_close - swing_high) <= threshold
        or abs(last_close - swing_low) <= threshold
    )


def calc_daily_trend(
    candles_1d: list[OHLCVCandle], fast: int = 20, slow: int = 50
) -> str:
    """Направление дневного тренда по EMA(fast) vs EMA(slow): 'up', 'down' или 'neutral'."""
    if len(candles_1d) < slow + 1:
        return "neutral"

    df = _to_df(candles_1d)
    ema_fast = ta.trend.EMAIndicator(df["close"], window=fast).ema_indicator()
    ema_slow = ta.trend.EMAIndicator(df["close"], window=slow).ema_indicator()

    last_fast = ema_fast.iloc[-1]
    last_slow = ema_slow.iloc[-1]

    if np.isnan(last_fast) or np.isnan(last_slow):
        return "neutral"

    if last_fast > last_slow:
        return "up"
    if last_fast < last_slow:
        return "down"
    return "neutral"


def calc_oi_trend(oi_history: list[OISnapshot], lookback: int = 8) -> str:
    """Тренд OI за последние lookback точек: 'growing', 'shrinking' или 'neutral'.

    Используется OI_CHANGE_4H_MIN_PCT как порог значимого изменения.
    """
    if len(oi_history) < lookback + 2:
        return "neutral"

    first_oi = oi_history[-(lookback + 1)].open_interest
    last_oi = oi_history[-1].open_interest

    if first_oi == 0:
        return "neutral"

    change_pct = (last_oi - first_oi) / first_oi

    if change_pct >= settings.OI_TREND_MIN_PCT:
        return "growing"
    if change_pct <= -settings.OI_TREND_MIN_PCT:
        return "shrinking"
    return "neutral"


def calc_funding_bias(funding_history: list[FundingRateHistoryEntry]) -> str:
    """Средняя ставка финансирования за всю историю: 'long_heavy', 'short_heavy' или 'neutral'."""
    if not funding_history:
        return "neutral"

    avg = sum(e.funding_rate for e in funding_history) / len(funding_history)

    if avg >= settings.FUNDING_RATE_HIGH:
        return "long_heavy"
    if avg <= settings.FUNDING_RATE_LOW:
        return "short_heavy"
    return "neutral"


def calc_cvd_trend(cvd_points: list[CVDPoint]) -> str:
    """Тренд CVD за последнюю треть окна: 'rising' (байеры), 'falling' (продавцы) или 'neutral'."""
    if len(cvd_points) < 4:
        return "neutral"

    n = max(4, len(cvd_points) // 3)
    first_cvd = cvd_points[-n].cvd
    last_cvd = cvd_points[-1].cvd

    if last_cvd > first_cvd:
        return "rising"
    if last_cvd < first_cvd:
        return "falling"
    return "neutral"


def calc_cvd_price_divergence(
    candles_4h: list[OHLCVCandle], cvd_points: list[CVDPoint]
) -> str | None:
    """Дивергенция цены и CVD за окно CVD.

    'bullish' — цена вниз, CVD положительный (продавцы выдыхаются).
    'bearish' — цена вверх, CVD отрицательный (байеры не подтверждают рост).
    """
    n = len(cvd_points)
    if n < 4 or len(candles_4h) < n:
        return None

    price_first = candles_4h[-n].close
    price_last = candles_4h[-1].close
    cvd_change = cvd_points[-1].cvd - cvd_points[0].cvd

    price_up = price_last > price_first
    cvd_positive = cvd_change > 0

    if price_up and not cvd_positive:
        return "bearish"
    if not price_up and cvd_positive:
        return "bullish"

    return None


def calc_liquidation_spike(
    liq_history: list[LiquidationHistoryPoint],
    window: int = settings.LIQ_SPIKE_WINDOW,
    multiplier: float = settings.LIQ_SPIKE_MULTIPLIER,
) -> bool:
    """True если суммарные ликвидации последней свечи превышают multiplier × среднее за window свечей.

    Всплеск = каскадные стоп-ауты → потенциальный разворот или ускорение тренда.
    """
    if len(liq_history) < window + 1:
        return False

    baseline = liq_history[-(window + 1) : -1]
    avg_total = sum(
        p.long_liquidation_usd + p.short_liquidation_usd for p in baseline
    ) / len(baseline)

    if avg_total == 0:
        return False

    last = liq_history[-1]
    last_total = last.long_liquidation_usd + last.short_liquidation_usd
    return last_total > multiplier * avg_total


def calc_oi_weighted_funding_bias(funding_hist: list[FundingRateOHLC]) -> str:
    """Средняя OI-взвешенная ставка финансирования: 'long_heavy', 'short_heavy' или 'neutral'.

    Точнее calc_funding_bias: взвешивает все биржи по их OI, не только Binance.
    """
    if not funding_hist:
        return "neutral"
    avg = sum(e.close for e in funding_hist) / len(funding_hist)
    if avg >= settings.FUNDING_RATE_HIGH:
        return "long_heavy"
    if avg <= settings.FUNDING_RATE_LOW:
        return "short_heavy"
    return "neutral"
