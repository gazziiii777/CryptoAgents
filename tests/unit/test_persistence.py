from datetime import datetime, timezone
from typing import cast

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.services.entry.fill import ExecutionService
from app.services.entry.models.fill_result import FillResult
from app.domain.models.analysis import CandidateSignal
from app.engines.worker.pipeline.persistence import persist_signals
from core.constants.decisions import REASON_SIGNAL_READY
from core.settings import settings
from db.models import Decision, EventType
from db.repositories.event_repo import EventRepo
from db.repositories.signal_repo import SignalRepo
from tests.fixtures.fx_signals import make_candidate_signal

_SYMBOL = "ZEC/USDT:USDT"
_BAR = datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc)


class _PassthroughExecution:
    async def resolve_fill(self, candidate_signal: CandidateSignal) -> FillResult:
        return FillResult(
            candidate_signal.final_signal, candidate_signal.decision_reason
        )


def _execution() -> ExecutionService:
    return cast(ExecutionService, _PassthroughExecution())


def _candidate_signal() -> CandidateSignal:
    return make_candidate_signal()


async def test_persist_creates_signal_and_snapshot_event(session: AsyncSession):
    persisted = await persist_signals(session, [_candidate_signal()], _execution())
    assert len(persisted) == 1

    signal = await SignalRepo(session).get_by_symbol_bar(_SYMBOL, _BAR)
    assert signal is not None
    assert signal.confluence_score == pytest.approx(settings.CONFIDENCE_SHRINKAGE)
    assert signal.decision == Decision.NO_TRADE
    assert signal.decision_reason == REASON_SIGNAL_READY
    assert signal.crypto_setup_json is not None
    assert signal.crypto_setup_json["entry_price"] == 101.0

    events = await EventRepo(session).list_by_entity("signal", signal.id)
    assert len(events) == 1
    assert events[0].event_type == EventType.SIGNAL_GENERATED
    assert events[0].payload_json["synthesis"]["overall_bias"] == "Bullish"


async def test_persist_is_idempotent_per_bar(session: AsyncSession):
    candidate_signal = _candidate_signal()
    assert len(await persist_signals(session, [candidate_signal], _execution())) == 1
    assert len(await persist_signals(session, [candidate_signal], _execution())) == 0


def _ranked_candidate(symbol: str, analyst_confluence: float) -> CandidateSignal:
    base = _candidate_signal()
    candidate = base.candidate.model_copy(update={"symbol": symbol})
    synthesis = base.synthesis.model_copy(
        update={"analyst_confluence": analyst_confluence}
    )
    return base.model_copy(update={"candidate": candidate, "synthesis": synthesis})


async def test_persist_ranks_by_analyst_confluence(session: AsyncSession):
    low = _ranked_candidate("AAA/USDT:USDT", 0.20)
    high = _ranked_candidate("BBB/USDT:USDT", 0.70)
    persisted = await persist_signals(session, [low, high], _execution())
    order = [candidate_signal.candidate.symbol for candidate_signal, _ in persisted]
    assert order == ["BBB/USDT:USDT", "AAA/USDT:USDT"]
