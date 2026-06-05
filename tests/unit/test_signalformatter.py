from app.domain.models.analysis import SignalSynthesis
from app.domain.models.setup import CryptoSetup
from app.domain.synthesis.signalformatter import format_signal


def test_format_signal_combines_setup_and_synthesis():
    synthesis = SignalSynthesis(
        overall_bias="Bullish",
        confluence_score=0.8,
        analyst_confluence=0.65,
        has_significant_conflict=False,
        scores_by_analyst={"macro": 1.0, "technical": 1.0},
        top_risks=["low liquidity"],
        reasoning="all analysts bullish",
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
        leverage_intent="aggressive",
    )

    signal = format_signal("ZEC/USDT:USDT", synthesis, setup)

    assert signal.symbol == "ZEC/USDT:USDT"
    assert signal.direction == "long"
    assert signal.entry_price == 101.0
    assert signal.confluence_score == 0.8
    assert signal.analyst_confluence == 0.65
    assert signal.thesis == "all analysts bullish"
    assert signal.key_risks == ["low liquidity"]
    assert signal.leverage_intent == "aggressive"
