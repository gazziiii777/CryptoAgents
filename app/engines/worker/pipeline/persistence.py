import logging
from typing import cast

from sqlmodel.ext.asyncio.session import AsyncSession

from app.services.entry.fill import ExecutionService
from app.domain.models.analysis import CandidateSignal
from app.services.positions.account_service import ensure_default_account
from app.services.entry.manager import PortfolioManager
from core.constants.decisions import REASON_SIGNAL_READY, REASON_TRADING_HALTED
from core.constants.entities import ENTITY_SIGNAL
from db.models import Account, Decision, Direction, EventType, Signal, SignalSource
from db.repositories.event_repo import EventRepo
from db.repositories.signal_repo import SignalRepo
from db.repositories.system_state_repo import SystemStateRepo

logger = logging.getLogger(__name__)

_BIAS_TO_DIRECTION = {
    "Bullish": Direction.LONG,
    "Bearish": Direction.SHORT,
    "Neutral": Direction.NO_TRADE,
}


async def persist_signals(
    session: AsyncSession, signals: list[CandidateSignal], execution: ExecutionService
) -> list[tuple[CandidateSignal, Signal]]:
    """Пишет Signal + Event(snapshot) и прогоняет PortfolioManager по готовым сигналам.

    Идемпотентно по (symbol, bar_close_ts). Для signal_ready ExecutionService пере-резолвит
    вход по живой цене, затем PM выносит реальный Decision (taken/skipped_*) и открывает
    VirtualPosition; halt-флаг переводит всё в NO_TRADE(trading_halted). Прочие исходы
    цепочки остаются NO_TRADE с их reason. ExecutionService инжектится — его CcxtClient
    держит вызывающий (run_pipeline). Возвращает (candidate, signal) для research-БД.
    """
    account = await ensure_default_account(session)
    halted = (await SystemStateRepo(session).get_or_create()).halted
    manager = PortfolioManager(session)
    signal_repo = SignalRepo(session)
    event_repo = EventRepo(session)

    ranked = sorted(
        signals, key=lambda cs: cs.synthesis.analyst_confluence, reverse=True
    )
    persisted: list[tuple[CandidateSignal, Signal]] = []
    for candidate_signal in ranked:
        symbol = candidate_signal.candidate.symbol
        if await signal_repo.get_by_symbol_bar(symbol, candidate_signal.bar_close_ts):
            logger.info("signal already persisted, skipping symbol=%s", symbol)
            continue
        signal = await _create_signal(signal_repo, candidate_signal)
        await event_repo.append(
            event_type=EventType.SIGNAL_GENERATED,
            entity_type=ENTITY_SIGNAL,
            entity_id=signal.id,
            payload=candidate_signal.model_dump(mode="json"),
        )
        await _apply_decision(
            manager, execution, account, signal, candidate_signal, halted
        )
        persisted.append((candidate_signal, signal))
    logger.info("persisted %d signals", len(persisted))
    return persisted


async def _create_signal(
    signal_repo: SignalRepo, candidate_signal: CandidateSignal
) -> Signal:
    synthesis = candidate_signal.synthesis
    intent = candidate_signal.setup_intent
    setup = candidate_signal.crypto_setup
    final = candidate_signal.final_signal
    direction = (
        Direction(final.direction)
        if final is not None
        else _BIAS_TO_DIRECTION[synthesis.overall_bias]
    )
    return await signal_repo.create(
        Signal(
            symbol=candidate_signal.candidate.symbol,
            bar_close_ts=candidate_signal.bar_close_ts,
            source=SignalSource.SCREENER,
            screener_score=candidate_signal.candidate.screener.score,
            confluence_score=synthesis.confluence_score,
            direction=direction,
            decision=Decision.NO_TRADE,
            decision_reason=candidate_signal.decision_reason,
            setup_intent_json=intent.model_dump(mode="json") if intent else None,
            crypto_setup_json=setup.model_dump(mode="json") if setup else None,
        )
    )


async def _apply_decision(
    manager: PortfolioManager,
    execution: ExecutionService,
    account: Account,
    signal: Signal,
    candidate_signal: CandidateSignal,
    halted: bool,
) -> None:
    """signal_ready: пере-резолвит вход по живой цене, затем выносит решение PM.

    Перед открытием ExecutionService тянет живую цену и пере-заякоривает уровни (фикс
    протухания за время прогона агентов); drift-гейт / нерезолвимость → NO_TRADE с
    соответствующим reason. Иначе PM открывает уже по свежему FinalSignal. Прочие
    исходы цепочки остаются NO_TRADE с их reason.
    """
    final = candidate_signal.final_signal
    if candidate_signal.decision_reason != REASON_SIGNAL_READY or final is None:
        return
    if halted:
        signal.decision = Decision.NO_TRADE
        signal.decision_reason = REASON_TRADING_HALTED
        return
    fill = await execution.resolve_fill(candidate_signal)
    if fill.final_signal is None:
        signal.decision = Decision.NO_TRADE
        signal.decision_reason = fill.reason
        return
    decision = await manager.evaluate(
        account=account,
        signal_id=cast(int, signal.id),
        final_signal=fill.final_signal,
        funding_rate=candidate_signal.candidate.screener.signals.funding_rate,
        bar_close_ts=candidate_signal.bar_close_ts,
    )
    signal.decision = decision
    signal.decision_reason = decision.value
