from datetime import datetime

from sqlalchemy import Boolean, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.research.base import ResearchBase
from db.types import UTCDateTime


class SignalRecord(ResearchBase):
    """Строка на каждого оценённого кандидата: весь контекст решения для исследований."""

    __tablename__ = "signal_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime)
    bar_close_ts: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    trading_signal_id: Mapped[int | None] = mapped_column(Integer, index=True)
    strategy_version: Mapped[str] = mapped_column(String(32))

    screener_score: Mapped[int | None] = mapped_column(Integer)
    screener_direction: Mapped[str | None] = mapped_column(String(16))
    adx: Mapped[float | None] = mapped_column(Float)
    funding_rate: Mapped[float | None] = mapped_column(Float)
    rsi_level: Mapped[float | None] = mapped_column(Float)
    oi_trend: Mapped[str | None] = mapped_column(String(16))
    cvd_trend: Mapped[str | None] = mapped_column(String(16))
    long_short_ratio: Mapped[float | None] = mapped_column(Float)

    volume_spike: Mapped[bool | None] = mapped_column(Boolean)
    bb_squeeze: Mapped[bool | None] = mapped_column(Boolean)
    near_swing: Mapped[bool | None] = mapped_column(Boolean)
    liq_spike: Mapped[bool | None] = mapped_column(Boolean)
    ema_cross: Mapped[str | None] = mapped_column(String(8))
    rsi_divergence: Mapped[str | None] = mapped_column(String(8))
    macd: Mapped[str | None] = mapped_column(String(8))
    vwap_bias: Mapped[str | None] = mapped_column(String(8))
    daily_trend: Mapped[str | None] = mapped_column(String(8))
    cvd_price_divergence: Mapped[str | None] = mapped_column(String(8))
    funding_bias: Mapped[str | None] = mapped_column(String(16))
    oi_weighted_funding_bias: Mapped[str | None] = mapped_column(String(16))
    oi_change_4h_pct: Mapped[float | None] = mapped_column(Float)
    top_trader_ls_ratio: Mapped[float | None] = mapped_column(Float)
    basis: Mapped[float | None] = mapped_column(Float)
    smart_money_divergence: Mapped[str | None] = mapped_column(String(20))
    positioning_regime: Mapped[str | None] = mapped_column(String(20))
    squeeze_setup: Mapped[str | None] = mapped_column(String(20))
    spot_perp_divergence: Mapped[str | None] = mapped_column(String(8))
    book_imbalance: Mapped[float | None] = mapped_column(Float)
    liq_magnet_above: Mapped[float | None] = mapped_column(Float)
    liq_magnet_below: Mapped[float | None] = mapped_column(Float)
    pump_risk: Mapped[str | None] = mapped_column(String(8))

    macro_bias: Mapped[str] = mapped_column(String(16))
    macro_regime: Mapped[str] = mapped_column(String(32))
    derivatives_bias: Mapped[str] = mapped_column(String(16))
    sentiment_bias: Mapped[str] = mapped_column(String(16))
    technical_bias: Mapped[str] = mapped_column(String(16))
    technical_confidence: Mapped[float] = mapped_column(Float)

    confluence_score: Mapped[float] = mapped_column(Float, index=True)
    analyst_confluence: Mapped[float | None] = mapped_column(Float)
    overall_bias: Mapped[str] = mapped_column(String(16))
    has_conflict: Mapped[bool] = mapped_column(Boolean)
    synthesis_reasoning: Mapped[str] = mapped_column(Text)
    top_risks: Mapped[str | None] = mapped_column(Text)

    trader_verdict: Mapped[str | None] = mapped_column(String(12))
    trader_conviction: Mapped[float | None] = mapped_column(Float)
    da_critical_count: Mapped[int | None] = mapped_column(Integer)
    llm_provider: Mapped[str | None] = mapped_column(String(16))

    decision: Mapped[str] = mapped_column(String(24), index=True)
    decision_reason: Mapped[str | None] = mapped_column(String(256))
    direction: Mapped[str | None] = mapped_column(String(8))
    setup_type: Mapped[str | None] = mapped_column(String(32))
    entry_price: Mapped[float | None] = mapped_column(Float)
    stop_price: Mapped[float | None] = mapped_column(Float)
    target_price: Mapped[float | None] = mapped_column(Float)
    risk_reward: Mapped[float | None] = mapped_column(Float)
    valid_hours: Mapped[int | None] = mapped_column(Integer)
