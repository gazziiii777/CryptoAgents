from pydantic import BaseModel, ConfigDict

from app.models.screener import DailyTrend, EmaCross, MacdSignal, RsiDivergence


class TechnicalFacts(BaseModel):
    """Детерминированные технические уровни/факты для LLM-интерпретации."""

    model_config = ConfigDict(frozen=True)

    current_price: float
    atr: float
    ema_20: float
    ema_50: float
    recent_high: float
    recent_low: float
    prev_day_high: float
    prev_day_low: float
    adx: float
    rsi: float | None
    rsi_divergence: RsiDivergence | None
    macd: MacdSignal | None
    ema_cross: EmaCross | None
    daily_trend: DailyTrend
