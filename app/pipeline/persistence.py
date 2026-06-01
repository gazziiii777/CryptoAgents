import logging
from typing import cast

from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.analysis import CandidateSignal
from app.portfolio.account_service import ensure_default_account
from app.portfolio.manager import PortfolioManager
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
    session: AsyncSession, signals: list[CandidateSignal]
) -> list[tuple[CandidateSignal, Signal]]:
    """Пишет Signal + Event(snapshot) и прогоняет PortfolioManager по готовым сигналам.

    Идемпотентно по (symbol, bar_close_ts). Для signal_ready PM выносит реальный
    Decision (taken/skipped_*) и открывает VirtualPosition; halt-флаг переводит всё в
    NO_TRADE(trading_halted). Прочие исходы цепочки остаются NO_TRADE с их reason.
    Возвращает (candidate, signal) персистнутых сигналов — для записи в research-БД.
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
        await _apply_decision(manager, account, signal, candidate_signal, halted)
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
    account: Account,
    signal: Signal,
    candidate_signal: CandidateSignal,
    halted: bool,
) -> None:
    """Для signal_ready выносит решение PM; иначе Signal остаётся NO_TRADE."""
    final = candidate_signal.final_signal
    if candidate_signal.decision_reason != REASON_SIGNAL_READY or final is None:
        return
    if halted:
        signal.decision = Decision.NO_TRADE
        signal.decision_reason = REASON_TRADING_HALTED
        return
    decision = await manager.evaluate(
        account=account,
        signal_id=cast(int, signal.id),
        final_signal=final,
        funding_rate=candidate_signal.candidate.screener.signals.funding_rate,
        bar_close_ts=candidate_signal.bar_close_ts,
    )
    signal.decision = decision
    signal.decision_reason = decision.value
