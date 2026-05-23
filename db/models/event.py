from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from db._time import utcnow
from db.models._enums import EventType
from db.types import UTCDateTime


class Event(SQLModel, table=True):
    __tablename__ = "event"

    id: int | None = Field(default=None, primary_key=True)
    ts: datetime = Field(
        default_factory=utcnow, sa_column=Column(UTCDateTime, nullable=False, index=True)
    )

    event_type: EventType = Field(index=True)
    entity_type: str | None = Field(default=None, max_length=32, index=True)
    entity_id: int | None = Field(default=None, index=True)

    payload_json: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
