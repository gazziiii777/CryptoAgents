from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Column, ForeignKey, Index, text
from sqlmodel import Field, SQLModel

from db.models._enums import ExitReason, PositionSide, PositionState
from db.types import DecimalText, UTCDateTime

_OPEN_PREDICATE = text(f"state = '{PositionState.OPEN.value}'")


class VirtualPosition(SQLModel, table=True):
    __tablename__ = "virtual_position"
    __table_args__ = (
        Index(
            "ux_position_open_per_symbol",
            "account_id",
            "symbol",
            unique=True,
            sqlite_where=_OPEN_PREDICATE,
            postgresql_where=_OPEN_PREDICATE,
        ),
        Index("ix_position_state", "state"),
    )

    id: int | None = Field(default=None, primary_key=True)
    account_id: int = Field(sa_column=Column(ForeignKey("account.id"), nullable=False, index=True))

    symbol: str = Field(max_length=32)
    side: PositionSide
    state: PositionState = Field(default=PositionState.OPEN)

    entry_signal_id: int = Field(sa_column=Column(ForeignKey("signal.id"), nullable=False))

    entry_ts: datetime = Field(sa_column=Column(UTCDateTime, nullable=False))
    entry_price: Decimal = Field(sa_column=Column(DecimalText, nullable=False))
    qty: Decimal = Field(sa_column=Column(DecimalText, nullable=False))

    stop_price: Decimal = Field(sa_column=Column(DecimalText, nullable=False))
    target_price: Decimal = Field(sa_column=Column(DecimalText, nullable=False))

    exit_ts: datetime | None = Field(default=None, sa_column=Column(UTCDateTime, nullable=True))
    exit_price: Decimal | None = Field(
        default=None, sa_column=Column(DecimalText, nullable=True)
    )
    exit_reason: ExitReason | None = Field(default=None)

    realized_pnl: Decimal | None = Field(
        default=None, sa_column=Column(DecimalText, nullable=True)
    )
    simulated_fees: Decimal | None = Field(
        default=None, sa_column=Column(DecimalText, nullable=True)
    )
    simulated_funding: Decimal | None = Field(
        default=None, sa_column=Column(DecimalText, nullable=True)
    )
