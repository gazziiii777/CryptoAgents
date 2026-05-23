from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class OISnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    timestamp: int
    open_interest: float
    open_interest_value: float


class LongShortRatio(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    timestamp: int
    long_short_ratio: float
    long_account: float
    short_account: float


class CVDPoint(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    timestamp: int
    cvd: float
