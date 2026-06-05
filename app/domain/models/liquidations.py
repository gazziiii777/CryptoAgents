from pydantic import BaseModel, ConfigDict


class NormalizedLiquidation(BaseModel):
    model_config = ConfigDict(frozen=True)

    exchange: str
    symbol: str
    order_side: str
    liquidated_side: str
    price: float
    quantity: float
    trade_time_ms: int
