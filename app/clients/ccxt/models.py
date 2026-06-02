from pydantic import AliasPath, BaseModel, ConfigDict, Field


class CcxtMarket(BaseModel):
    """Подмножество рыночного описания ccxt load_markets() для фильтра вселенной."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    swap: bool = False
    base: str = ""
    quote: str
    active: bool | None = None
    underlying_type: str | None = Field(
        default=None, validation_alias=AliasPath("info", "underlyingType")
    )


class CcxtTicker(BaseModel):
    """Подмножество тикера ccxt fetch_tickers() — нужен только объём в quote-валюте."""

    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    quote_volume: float | None = Field(default=None, alias="quoteVolume")


class OHLCVCandle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class FundingRateHistoryEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    timestamp: int
    funding_rate: float
