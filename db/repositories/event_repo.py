from datetime import datetime
from typing import Any

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from db.models import Event, EventType

_DEFAULT_ENTITY_HISTORY_LIMIT = 100
_MAX_EVENTS_SINCE = 10_000


class EventRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(
        self,
        *,
        event_type: EventType,
        entity_type: str | None = None,
        entity_id: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Event:
        event = Event(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            payload_json=payload,
        )
        self._session.add(event)
        await self._session.flush()
        return event

    async def list_by_entity(
        self,
        entity_type: str,
        entity_id: int,
        limit: int = _DEFAULT_ENTITY_HISTORY_LIMIT,
    ) -> list[Event]:
        result = await self._session.exec(
            select(Event)
            .where(Event.entity_type == entity_type, Event.entity_id == entity_id)
            .order_by(col(Event.ts).desc())
            .limit(limit)
        )
        return list(result.all())

    async def list_by_type_since(
        self, event_type: EventType, since: datetime, limit: int = _MAX_EVENTS_SINCE
    ) -> list[Event]:
        result = await self._session.exec(
            select(Event)
            .where(Event.event_type == event_type, Event.ts >= since)
            .order_by(col(Event.ts).desc())
            .limit(limit)
        )
        return list(result.all())
