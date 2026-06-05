from pydantic import BaseModel


class RegimePerformance(BaseModel):
    regime: str
    trades: int
    win_rate: float
    avg_r: float
    total_r: float
    avg_mfe_r: float | None
    avg_holding_hours: float
