from datetime import datetime, timezone

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.aggregator import aggregate_signals
from app.enricher.insight import derive_social_insight
from app.models.analysis import (
    CandidateSignal,
    DerivativesReport,
    MacroReport,
    SentimentReport,
    TechnicalReport,
)
from app.models.enricher import EnrichedCandidate
from app.models.screener import ScreenerResult, empty_signals
from app.models.setup import CryptoSetup
from app.pipeline.persistence import persist_signals
from core.constants.decisions import REASON_SIGNAL_READY
from core.settings import settings
from db.models import Decision, EventType
from db.repositories.event_repo import EventRepo
from db.repositories.signal_repo import SignalRepo

_SYMBOL = "ZEC/USDT:USDT"
_BAR = datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc)


def _candidate_signal() -> CandidateSignal:
    screener = ScreenerResult(
        symbol=_SYMBOL,
        gate_passed=True,
        score=7,
        adx=30.0,
        direction="long",
        signals=empty_signals(),
    )
    social = derive_social_insight(
        lc=None,
        news=[],
        posts=[],
        whatsup=None,
        time_series=[],
        screener_direction="long",
    )
    candidate = EnrichedCandidate(
        symbol=_SYMBOL, screener=screener, social=social, enriched_at=_BAR
    )
    macro = MacroReport(
        reasoning="r",
        regime="Ranging",
        btc_bias="Bullish",
        dominance_trend="Flat",
        alts_tradeable=True,
    )
    deriv = DerivativesReport(
        key_insight="k",
        funding_signal="Neutral",
        oi_signal="Neutral",
        ls_signal="Balanced",
        liq_nearest_long=None,
        liq_nearest_short=None,
        cvd_direction="Neutral",
        overall_bias="Bullish",
    )
    senti = SentimentReport(
        key_insight="k",
        social_sentiment="Bullish",
        fear_greed_label="Neutral",
        news_sentiment="Neutral",
        overall_bias="Bullish",
    )
    tech = TechnicalReport(
        market_structure="m",
        htf_bias="Bullish",
        setup_bias="Bullish",
        key_levels=[],
        entry_timeframe_note="n",
        signal_direction="Long",
        confidence=0.6,
    )
    synthesis = aggregate_signals(macro, deriv, senti, tech)
    setup = CryptoSetup(
        direction="long",
        setup_type="trend_continuation",
        entry_price=101.0,
        stop_price=100.0,
        target_price=103.0,
        risk_reward=2.0,
        valid_hours=8,
        funding_impact_pct=0.0006,
        invalidation="4h close below 100",
        leverage_intent="moderate",
    )
    return CandidateSignal(
        candidate=candidate,
        macro=macro,
        derivatives=deriv,
        sentiment=senti,
        technical=tech,
        synthesis=synthesis,
        bar_close_ts=_BAR,
        crypto_setup=setup,
        decision_reason=REASON_SIGNAL_READY,
    )


async def test_persist_creates_signal_and_snapshot_event(session: AsyncSession):
    persisted = await persist_signals(session, [_candidate_signal()])
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
    assert len(await persist_signals(session, [candidate_signal])) == 1
    assert len(await persist_signals(session, [candidate_signal])) == 0


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
    persisted = await persist_signals(session, [low, high])
    order = [candidate_signal.candidate.symbol for candidate_signal, _ in persisted]
    assert order == ["BBB/USDT:USDT", "AAA/USDT:USDT"]
