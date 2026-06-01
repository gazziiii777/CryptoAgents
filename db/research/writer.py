import logging
from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import CandidateSignal
from core.constants.time import SECONDS_PER_HOUR
from core.settings import settings
from db.models import Signal, VirtualPosition
from db.research.engine import research_session_scope
from db.research.models import AgentOutput, SignalRecord, TradeOutcome

logger = logging.getLogger(__name__)


def _enum_value(value: Enum | str) -> str:
    """Строковое значение enum-члена (или str(value) для не-enum) для research-колонок."""
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def _build_signal_record(
    candidate_signal: CandidateSignal, signal: Signal
) -> SignalRecord:
    screener = candidate_signal.candidate.screener
    signals = screener.signals
    synthesis = candidate_signal.synthesis
    setup = candidate_signal.crypto_setup
    technical = candidate_signal.technical
    verdict = candidate_signal.trader_verdict
    da = candidate_signal.devils_advocate
    return SignalRecord(
        ts=signal.ts,
        bar_close_ts=candidate_signal.bar_close_ts,
        symbol=candidate_signal.candidate.symbol,
        trading_signal_id=signal.id,
        strategy_version=signal.strategy_version,
        screener_score=screener.score,
        screener_direction=_enum_value(screener.direction),
        adx=screener.adx,
        funding_rate=signals.funding_rate,
        rsi_level=signals.rsi_level,
        oi_trend=_enum_value(signals.oi_trend),
        cvd_trend=_enum_value(signals.cvd_trend),
        long_short_ratio=signals.long_short_ratio,
        volume_spike=signals.volume_spike,
        bb_squeeze=signals.bb_squeeze,
        near_swing=signals.near_swing,
        liq_spike=signals.liq_spike,
        ema_cross=signals.ema_cross,
        rsi_divergence=signals.rsi_divergence,
        macd=signals.macd,
        vwap_bias=signals.vwap_bias,
        daily_trend=signals.daily_trend,
        cvd_price_divergence=signals.cvd_price_divergence,
        funding_bias=signals.funding_bias,
        oi_weighted_funding_bias=signals.oi_weighted_funding_bias,
        oi_change_4h_pct=signals.oi_change_4h_pct,
        top_trader_ls_ratio=signals.top_trader_ls_ratio,
        basis=signals.basis,
        smart_money_divergence=signals.smart_money_divergence,
        pump_risk=candidate_signal.candidate.social.pump_risk,
        macro_bias=candidate_signal.macro.btc_bias,
        macro_regime=candidate_signal.macro.regime,
        derivatives_bias=candidate_signal.derivatives.overall_bias,
        sentiment_bias=candidate_signal.sentiment.overall_bias,
        technical_bias=technical.signal_direction,
        technical_confidence=technical.confidence,
        confluence_score=synthesis.confluence_score,
        analyst_confluence=synthesis.analyst_confluence,
        overall_bias=synthesis.overall_bias,
        has_conflict=synthesis.has_significant_conflict,
        synthesis_reasoning=synthesis.reasoning,
        top_risks="; ".join(synthesis.top_risks) if synthesis.top_risks else None,
        trader_verdict=verdict.verdict if verdict else None,
        trader_conviction=verdict.conviction if verdict else None,
        da_critical_count=len(da.critical_risks) if da else None,
        llm_provider=settings.LLM_PROVIDER.value,
        decision=_enum_value(signal.decision),
        decision_reason=signal.decision_reason,
        direction=setup.direction if setup else None,
        setup_type=setup.setup_type if setup else None,
        entry_price=setup.entry_price if setup else None,
        stop_price=setup.stop_price if setup else None,
        target_price=setup.target_price if setup else None,
        risk_reward=setup.risk_reward if setup else None,
        valid_hours=setup.valid_hours if setup else None,
    )


def _build_agent_outputs(
    candidate_signal: CandidateSignal, signal_record_id: int
) -> list[AgentOutput]:
    scores = candidate_signal.synthesis.scores_by_analyst
    rows = [
        (
            "macro",
            candidate_signal.macro.btc_bias,
            None,
            candidate_signal.macro.reasoning,
        ),
        (
            "derivatives",
            candidate_signal.derivatives.overall_bias,
            None,
            candidate_signal.derivatives.key_insight,
        ),
        (
            "sentiment",
            candidate_signal.sentiment.overall_bias,
            None,
            candidate_signal.sentiment.key_insight,
        ),
        (
            "technical",
            candidate_signal.technical.signal_direction,
            candidate_signal.technical.confidence,
            candidate_signal.technical.market_structure,
        ),
    ]
    return [
        AgentOutput(
            signal_record_id=signal_record_id,
            symbol=candidate_signal.candidate.symbol,
            bar_close_ts=candidate_signal.bar_close_ts,
            agent_name=name,
            bias=bias,
            confidence=confidence,
            score=scores.get(name),
            key_insight=insight,
        )
        for name, bias, confidence, insight in rows
    ]


async def record_signals(rows: list[tuple[CandidateSignal, Signal]]) -> None:
    """Пишет signal_record + agent_output для каждого сигнала. Сбой не ломает торговлю."""
    if not rows:
        return
    try:
        async with research_session_scope() as session:
            for candidate_signal, signal in rows:
                record = _build_signal_record(candidate_signal, signal)
                session.add(record)
                await session.flush()
                for output in _build_agent_outputs(candidate_signal, record.id):
                    session.add(output)
    except Exception:
        logger.error("research: failed to record signals", exc_info=True)


async def record_trade_outcome(
    position: VirtualPosition,
    *,
    exit_price: Decimal,
    exit_ts: datetime,
    exit_reason: str,
    realized_pnl: Decimal,
    fees: Decimal,
    funding: Decimal,
    mfe_r: float,
) -> None:
    """Пишет trade_outcome закрытой позиции (R-multiple, время). Сбой не ломает торговлю."""
    try:
        risk = abs(position.entry_price - position.stop_price) * position.qty
        r_multiple = float(realized_pnl / risk) if risk > 0 else 0.0
        holding_hours = (exit_ts - position.entry_ts).total_seconds() / SECONDS_PER_HOUR
        async with research_session_scope() as session:
            record_id, setup_type = await _find_signal_record_meta(
                session, position.entry_signal_id
            )
            session.add(
                TradeOutcome(
                    signal_record_id=record_id,
                    trading_signal_id=position.entry_signal_id,
                    symbol=position.symbol,
                    side=_enum_value(position.side),
                    setup_type=setup_type,
                    leverage=position.leverage,
                    entry_price=float(position.entry_price),
                    exit_price=float(exit_price),
                    stop_price=float(position.stop_price),
                    target_price=float(position.target_price),
                    exit_reason=exit_reason,
                    realized_pnl=float(realized_pnl),
                    r_multiple=r_multiple,
                    max_favorable_excursion_r=mfe_r,
                    holding_hours=holding_hours,
                    simulated_fees=float(fees),
                    simulated_funding=float(funding),
                    entry_ts=position.entry_ts,
                    exit_ts=exit_ts,
                )
            )
    except Exception:
        logger.error(
            "research: failed to record outcome for %s", position.symbol, exc_info=True
        )


async def _find_signal_record_meta(
    session: AsyncSession, trading_signal_id: int
) -> tuple[int | None, str | None]:
    """(signal_record_id, setup_type) последнего record'а по trading_signal_id."""
    result = await session.execute(
        select(SignalRecord.id, SignalRecord.setup_type)
        .where(SignalRecord.trading_signal_id == trading_signal_id)
        .order_by(SignalRecord.id.desc())
        .limit(1)
    )
    row = result.first()
    if row is None:
        return None, None
    return row[0], row[1]
