from pydantic import BaseModel, ConfigDict, Field

_FROZEN = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)


class OISnapshot(BaseModel):
    model_config = _FROZEN

    timestamp: int
    open_interest: float = Field(alias="sumOpenInterest")
    open_interest_value: float = Field(alias="sumOpenInterestValue")


class LongShortRatio(BaseModel):
    model_config = _FROZEN

    timestamp: int
    long_short_ratio: float = Field(alias="longShortRatio")
    long_account: float = Field(alias="longAccount")
    short_account: float = Field(alias="shortAccount")


class CVDPoint(BaseModel):
    model_config = _FROZEN

    timestamp: int
    cvd: float
