from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel

from db._time import utcnow
from db.models._enums import Decision, Direction, SignalSource
from db.types import UTCDateTime


class Signal(SQLModel, table=True):
    __tablename__ = "signal"
    __table_args__ = (
        UniqueConstraint("symbol", "bar_close_ts", name="ux_signal_symbol_bar"),
    )

    id: int | None = Field(default=None, primary_key=True)
    ts: datetime = Field(
        default_factory=utcnow, sa_column=Column(UTCDateTime, nullable=False, index=True)
    )
    bar_close_ts: datetime = Field(sa_column=Column(UTCDateTime, nullable=False))

    symbol: str = Field(index=True, max_length=32)
    source: SignalSource = Field(default=SignalSource.SCREENER)

    screener_score: int | None = None
    confluence_score: float | None = None
    direction: Direction = Field(default=Direction.NO_TRADE)

    setup_intent_json: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    crypto_setup_json: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )

    decision: Decision = Field(default=Decision.NO_TRADE)
    decision_reason: str | None = Field(default=None, max_length=256)
    strategy_version: str = Field(default="1.0.0", max_length=32)
