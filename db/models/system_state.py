from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column
from sqlmodel import Field, SQLModel

from db._time import utcnow
from db.types import UTCDateTime

SYSTEM_STATE_ID = 1


class SystemState(SQLModel, table=True):
    __tablename__ = "system_state"

    id: int | None = Field(default=SYSTEM_STATE_ID, primary_key=True)
    halted: bool = Field(default=False)
    halt_reason: str | None = Field(default=None, max_length=256)
    updated_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UTCDateTime, nullable=False)
    )
