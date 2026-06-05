from pydantic import BaseModel, ConfigDict

_FROZEN = ConfigDict(frozen=True, extra="ignore")


class CoinGeckoGlobalData(BaseModel):
    """Поле data ответа /global: доминация по капитализации и её суточное изменение."""

    model_config = _FROZEN

    market_cap_percentage: dict[str, float]
    market_cap_change_percentage_24h_usd: float | None = None


class CoinGeckoGlobalResponse(BaseModel):
    model_config = _FROZEN

    data: CoinGeckoGlobalData


class CoinGeckoMarketEntry(BaseModel):
    """Элемент ответа /coins/markets: цена и изменения за окна."""

    model_config = _FROZEN

    current_price: float
    price_change_percentage_24h: float | None = None
    price_change_percentage_7d_in_currency: float | None = None


class MacroSnapshot(BaseModel):
    model_config = _FROZEN

    btc_dominance: float
    btc_price_usd: float
    btc_change_24h: float
    btc_change_7d: float
    total_market_cap_change_24h: float
