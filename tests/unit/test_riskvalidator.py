from app.models.setup import CryptoSetup
from app.riskvalidator import validate_risk


def _setup(risk_reward: float = 2.0, funding_impact_pct: float = 0.0006) -> CryptoSetup:
    return CryptoSetup(
        direction="long",
        setup_type="trend_continuation",
        entry_price=101.0,
        stop_price=100.0,
        target_price=103.0,
        risk_reward=risk_reward,
        valid_hours=8,
        funding_impact_pct=funding_impact_pct,
        invalidation="4h close below 100",
        leverage_intent="moderate",
    )


def test_passes_good_setup():
    assert validate_risk(_setup()) is None


def test_rejects_low_risk_reward():
    reason = validate_risk(_setup(risk_reward=1.2))
    assert reason is not None
    assert "R:R" in reason


def test_rejects_extreme_funding():
    reason = validate_risk(_setup(funding_impact_pct=0.05))
    assert reason is not None
    assert "funding" in reason
