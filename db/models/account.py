from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Column
from sqlmodel import Field, SQLModel

from core.constants.markets import QUOTE_CURRENCY
from db._time import utcnow
from db.types import DecimalText, UTCDateTime


class Account(SQLModel, table=True):
    __tablename__ = "account"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True, max_length=64)
    base_currency: str = Field(default=QUOTE_CURRENCY, max_length=16)

    initial_balance: Decimal = Field(sa_column=Column(DecimalText, nullable=False))
    current_balance: Decimal = Field(sa_column=Column(DecimalText, nullable=False))
    equity: Decimal = Field(sa_column=Column(DecimalText, nullable=False))
    peak_nav: Decimal = Field(sa_column=Column(DecimalText, nullable=False))

    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UTCDateTime, nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UTCDateTime, nullable=False)
    )
