import pytest
from freezegun import freeze_time
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.clients.llm.models import LLMUsage
from app.llm_gateway.budget import DailyBudgetGuard
from app.llm_gateway.errors import LLMBudgetExceededError
from db.models import EventType
from db.repositories.event_repo import EventRepo

_FROZEN_NOON = "2026-05-24 12:00:00"


def _usage(cost: float) -> LLMUsage:
    return LLMUsage(
        model="claude-haiku-4-5",
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        cost_usd=cost,
        latency_ms=100,
    )


async def test_spent_today_sums_llm_call_costs(session: AsyncSession):
    with freeze_time(_FROZEN_NOON):
        repo = EventRepo(session)
        await repo.append(
            event_type=EventType.LLM_CALL, payload=_usage(0.10).model_dump()
        )
        await repo.append(
            event_type=EventType.LLM_CALL, payload=_usage(0.25).model_dump()
        )
        spent = await DailyBudgetGuard(session).spent_today()
    assert spent == pytest.approx(0.35)


async def test_spent_today_skips_malformed_payload(session: AsyncSession):
    with freeze_time(_FROZEN_NOON):
        repo = EventRepo(session)
        await repo.append(
            event_type=EventType.LLM_CALL, payload=_usage(0.40).model_dump()
        )
        await repo.append(event_type=EventType.LLM_CALL, payload={"garbage": True})
        spent = await DailyBudgetGuard(session).spent_today()
    assert spent == pytest.approx(0.40)


async def test_ensure_within_budget_passes_under_cap(session: AsyncSession):
    with freeze_time(_FROZEN_NOON):
        await EventRepo(session).append(
            event_type=EventType.LLM_CALL, payload=_usage(1.0).model_dump()
        )
        await DailyBudgetGuard(session).ensure_within_budget()


async def test_ensure_within_budget_raises_when_exceeded(session: AsyncSession):
    with freeze_time(_FROZEN_NOON):
        await EventRepo(session).append(
            event_type=EventType.LLM_CALL, payload=_usage(6.0).model_dump()
        )
        with pytest.raises(LLMBudgetExceededError, match="daily budget"):
            await DailyBudgetGuard(session).ensure_within_budget()
