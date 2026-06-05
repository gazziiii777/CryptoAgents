import logging
from typing import TypeVar

from pydantic import BaseModel

from app.adapters.clients.llm.client import LLMClient
from app.adapters.clients.llm.models import LLMUsage
from app.llm_gateway.budget import DailyBudgetGuard
from db.engine import session_scope
from db.models import EventType
from db.repositories.event_repo import EventRepo

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMService:
    """Единая дверь к LLM: budget gate → вызов клиента → запись Event(llm_call).

    Budget-проверка и запись затрат идут в отдельных короткоживущих сессиях, чтобы учёт
    расходов попадал в audit-лог независимо от транзакции сигнала (даже если она откатится).
    Сам сетевой вызов — вне транзакции БД.
    """

    def __init__(self, client: LLMClient | None = None) -> None:
        self._client = client or LLMClient()

    async def structured(
        self,
        *,
        model: str,
        system: str,
        user: str,
        response_model: type[T],
        entity_type: str | None = None,
        entity_id: int | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> T:
        async with session_scope() as session:
            await DailyBudgetGuard(session).ensure_within_budget()

        parsed, usage = await self._client.complete(
            model=model,
            system=system,
            user=user,
            response_model=response_model,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        await self._record(usage, entity_type, entity_id)
        return parsed

    async def _record(
        self, usage: LLMUsage, entity_type: str | None, entity_id: int | None
    ) -> None:
        async with session_scope() as session:
            await EventRepo(session).append(
                event_type=EventType.LLM_CALL,
                entity_type=entity_type,
                entity_id=entity_id,
                payload=usage.model_dump(),
            )
