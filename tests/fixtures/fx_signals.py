from datetime import datetime, timezone

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
from app.models.screener import ScreenerResult, SignalDetails, empty_signals
from app.models.setup import CryptoSetup
from core.constants.decisions import REASON_SIGNAL_READY

_SYMBOL = "ZEC/USDT:USDT"
_BAR = datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc)


def make_candidate_signal(signals: SignalDetails | None = None) -> CandidateSignal:
    """Готовый CandidateSignal для тестов персиста/research. signals — кастомный snapshot."""
    screener = ScreenerResult(
        symbol=_SYMBOL,
        gate_passed=True,
        score=7,
        adx=30.0,
        direction="long",
        signals=signals if signals is not None else empty_signals(),
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
    synthesis = aggregate_signals(
        macro=macro, derivatives=deriv, sentiment=senti, technical=tech
    )
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
