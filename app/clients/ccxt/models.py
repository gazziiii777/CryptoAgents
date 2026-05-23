from __future__ import annotations

from pydantic import BaseModel, ConfigDict


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
