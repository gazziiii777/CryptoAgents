from typing import Literal

from pydantic import BaseModel, ConfigDict

_FROZEN = ConfigDict(frozen=True, extra="ignore")

LiquidityKind = Literal[
    "buy_wall", "sell_wall", "long_liq_cluster", "short_liq_cluster"
]


class LiquidityLevel(BaseModel):
    model_config = _FROZEN

    price: float
    kind: LiquidityKind
    strength: float


class LiquidityMap(BaseModel):
    model_config = _FROZEN

    symbol: str
    mark_price: float
    walls: list[LiquidityLevel]
    liq_clusters: list[LiquidityLevel]
    nearest_magnet_above: LiquidityLevel | None = None
    nearest_magnet_below: LiquidityLevel | None = None
    nearest_sell_wall_above: LiquidityLevel | None = None
    nearest_buy_wall_below: LiquidityLevel | None = None
