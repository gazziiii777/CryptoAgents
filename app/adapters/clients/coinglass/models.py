from enum import IntEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

_FROZEN = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

_HEATMAP_CELL_LEN = 3


class OrderSide(IntEnum):
    BUY = 1
    SELL = 2


class OrderState(IntEnum):
    ACTIVE = 1
    FILLED = 2


class OIAggregatedCandle(BaseModel):
    """OHLC агрегированного OI по всем биржам. timestamp=ms, значения в USD."""

    model_config = _FROZEN

    timestamp: int = Field(alias="time")
    open: float
    high: float
    low: float
    close: float


class AggregatedCVDPoint(BaseModel):
    """CVD агрегированный по биржам. timestamp=ms, объёмы в USD. cvd_delta > 0 — байеры доминируют."""

    model_config = _FROZEN

    timestamp: int = Field(alias="time")
    agg_taker_buy_vol: float
    agg_taker_sell_vol: float
    cvd_delta: float = Field(alias="cum_vol_delta")


class TopPositionRatio(BaseModel):
    """L/S ratio топ-трейдеров по объёму позиций. timestamp=ms. long_short_ratio = long_percent / short_percent."""

    model_config = _FROZEN

    timestamp: int = Field(alias="time")
    long_percent: float = Field(alias="top_position_long_percent")
    short_percent: float = Field(alias="top_position_short_percent")
    long_short_ratio: float = Field(alias="top_position_long_short_ratio")


class FundingRateOHLC(BaseModel):
    """OHLC ставки финансирования. timestamp=ms, значения — raw rate (не %)."""

    model_config = _FROZEN

    timestamp: int = Field(alias="time")
    open: float
    high: float
    low: float
    close: float


class FuturesBasisPoint(BaseModel):
    """Базис фьючерс/спот. timestamp=ms, значения в %. close_basis > 0 = контанго, < 0 = бэквордация."""

    model_config = _FROZEN

    timestamp: int = Field(alias="time")
    open_basis: float
    close_basis: float
    open_change: float
    close_change: float


class NetPositionPoint(BaseModel):
    """Нетто-изменение позиций. timestamp=ms, значения в базовой валюте (BTC для BTC). > 0 = новые позиции открыты."""

    model_config = _FROZEN

    timestamp: int = Field(alias="time")
    net_long_change: float
    net_short_change: float
    net_position_change_cum: float


class LiquidationHeatmapCell(BaseModel):
    """Ячейка тепловой карты ликвидаций: индексы по осям x/y и объём в USD."""

    model_config = _FROZEN

    x_idx: float
    y_idx: float
    amount_usd: float


class LiquidationHeatmapData(BaseModel):
    """Тепловая карта ликвидаций. y_axis = ценовые уровни USD. Ячейки — триплеты [x_idx, y_idx, amount_usd]."""

    model_config = _FROZEN

    y_axis: list[float]
    liquidation_leverage_data: list[LiquidationHeatmapCell]

    @field_validator("liquidation_leverage_data", mode="before")
    @classmethod
    def _triplets_to_cells(cls, value: object) -> object:
        """Преобразует сырые триплеты [x, y, amount] из API в LiquidationHeatmapCell."""
        if not isinstance(value, list):
            return value
        cells: list[object] = []
        for item in value:
            if isinstance(item, list | tuple) and len(item) == _HEATMAP_CELL_LEN:
                cells.append({
                    "x_idx": item[0],
                    "y_idx": item[1],
                    "amount_usd": item[2],
                })
            else:
                cells.append(item)
        return cells


class MaxPainEntry(BaseModel):
    model_config = _FROZEN

    symbol: str
    price: float
    long_max_pain_price: float = Field(alias="long_max_pain_liq_price")
    long_max_pain_level: float = Field(alias="long_max_pain_liq_level")
    short_max_pain_price: float = Field(alias="short_max_pain_liq_price")
    short_max_pain_level: float = Field(alias="short_max_pain_liq_level")


class LargeOrderEntry(BaseModel):
    """Крупный лимитный ордер. order_side: 1=Buy, 2=Sell. order_state: 1=активен, 2=исполнен."""

    model_config = _FROZEN

    price: float
    current_usd_value: float
    start_time: int
    order_side: OrderSide
    order_state: OrderState


class FearGreedHistoryEntry(BaseModel):
    """Сырой ответ fear-greed-history: параллельные массивы времени, индекса и цены."""

    model_config = _FROZEN

    time_list: list[int]
    data_list: list[float]
    price_list: list[float]


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

    timestamp: int = Field(alias="time")
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

    timestamp: int = Field(alias="time")
    long_liquidation_usd: float = Field(alias="aggregated_long_liquidation_usd")
    short_liquidation_usd: float = Field(alias="aggregated_short_liquidation_usd")
