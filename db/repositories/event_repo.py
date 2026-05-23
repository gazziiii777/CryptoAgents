from __future__ import annotations

from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from db.models import Event, EventType


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
        self, entity_type: str, entity_id: int, limit: int = 100
    ) -> list[Event]:
        result = await self._session.exec(
            select(Event)
            .where(Event.entity_type == entity_type, Event.entity_id == entity_id)
            .order_by(Event.ts.desc())
            .limit(limit)
        )
        return list(result.all())
