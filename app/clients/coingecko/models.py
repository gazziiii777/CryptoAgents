from __future__ import annotations

from pydantic import BaseModel


class MacroSnapshot(BaseModel):
    btc_dominance: float
    btc_price_usd: float
    btc_change_24h: float
    btc_change_7d: float
    total_market_cap_change_24h: float
