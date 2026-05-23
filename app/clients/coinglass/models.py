from __future__ import annotations

from pydantic import BaseModel, ConfigDict

_FROZEN = ConfigDict(frozen=True, extra="ignore")


class OIAggregatedCandle(BaseModel):
    """OHLC агрегированного OI по всем биржам. timestamp=ms, значения в USD."""

    model_config = _FROZEN

    timestamp: int
    open: float
    high: float
    low: float
    close: float


class AggregatedCVDPoint(BaseModel):
    """CVD агрегированный по биржам. timestamp=ms, объёмы в USD. cvd_delta > 0 — байеры доминируют."""

    model_config = _FROZEN

    timestamp: int
    agg_taker_buy_vol: float
    agg_taker_sell_vol: float
    cvd_delta: float


class TopPositionRatio(BaseModel):
    """L/S ratio топ-трейдеров по объёму позиций. timestamp=ms. long_short_ratio = long_percent / short_percent."""

    model_config = _FROZEN

    timestamp: int
    long_percent: float
    short_percent: float
    long_short_ratio: float


class FundingRateOHLC(BaseModel):
    """OHLC ставки финансирования. timestamp=ms, значения — raw rate (не %)."""

    model_config = _FROZEN

    timestamp: int
    open: float
    high: float
    low: float
    close: float


class FuturesBasisPoint(BaseModel):
    """Базис фьючерс/спот. timestamp=ms, значения в %. close_basis > 0 = контанго, < 0 = бэквордация."""

    model_config = _FROZEN

    timestamp: int
    open_basis: float
    close_basis: float
    open_change: float
    close_change: float


class NetPositionPoint(BaseModel):
    """Нетто-изменение позиций. timestamp=ms, значения в базовой валюте (BTC для BTC). > 0 = новые позиции открыты."""

    model_config = _FROZEN

    timestamp: int
    net_long_change: float
    net_short_change: float
    net_position_change_cum: float


class LiquidationHeatmapData(BaseModel):
    """Тепловая карта ликвидаций. y_axis = ценовые уровни USD. liquidation_leverage_data = [[x_idx, y_idx, amount_usd]]."""

    model_config = _FROZEN

    y_axis: list[float]
    liquidation_leverage_data: list[list[float]]


class MaxPainEntry(BaseModel):
    model_config = _FROZEN

    symbol: str
    price: float
    long_max_pain_price: float
    long_max_pain_level: float
    short_max_pain_price: float
    short_max_pain_level: float


class LargeOrderEntry(BaseModel):
    """Крупный лимитный ордер. order_side: 1=Buy, 2=Sell. order_state: 1=активен, 2=исполнен."""

    model_config = _FROZEN

    price: float
    current_usd_value: float
    start_time: int
    order_side: int
    order_state: int


class FearGreedPoint(BaseModel):
    """Индекс страха/жадности. timestamp=ms. value: 0=Extreme Fear, 100=Extreme Greed."""

    model_config = _FROZEN

    timestamp: int
    value: float
    price: float


class AltcoinSeasonPoint(BaseModel):
    """Индекс сезона альткоинов. timestamp=ms. altcoin_index: >75=altcoin season, <25=bitcoin season."""

    model_config = _FROZEN

    timestamp: int
    altcoin_index: int


class FuturesSpotRatioPoint(BaseModel):
    """Соотношение объёма фьючерсов к споту. timestamp=ms. futures_spot_vol_ratio > 1 = деривативы доминируют."""

    model_config = _FROZEN

    timestamp: int
    futures_spot_vol_ratio: float
    futures_vol_usd: float
    spot_vol_usd: float


class TokenUnlockEntry(BaseModel):
    """Разблокировка токенов. next_unlock_date=ms. next_unlock_of_circulating: 0.0–1.0, >0.05 = значимое давление продаж."""

    model_config = _FROZEN

    symbol: str
    next_unlock_date: int
    next_unlock_tokens: float
    next_unlock_of_circulating: float


class LiquidationHistoryPoint(BaseModel):
    """История ликвидаций агрегированная. timestamp=ms, значения в USD."""

    model_config = _FROZEN

    timestamp: int
    long_liquidation_usd: float
    short_liquidation_usd: float
