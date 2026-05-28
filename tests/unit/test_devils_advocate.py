import pytest

from app.analysts.devils_advocate import apply_devils_advocate, run_devils_advocate
from app.models.analysis import DevilsAdvocateReport, SignalSynthesis
from app.models.setup import CryptoSetup


def _synthesis(confluence: float = 0.7) -> SignalSynthesis:
    return SignalSynthesis(
        overall_bias="Bullish",
        confluence_score=confluence,
        has_significant_conflict=False,
        scores_by_analyst={"macro": 1.0},
        top_risks=["existing risk"],
        reasoning="r",
    )


def _setup() -> CryptoSetup:
    return CryptoSetup(
        direction="long",
        setup_type="trend_continuation",
        entry_price=101.0,
        stop_price=100.0,
        target_price=103.0,
        risk_reward=2.0,
        valid_hours=8,
        funding_impact_pct=0.0,
        invalidation="4h close below 100",
        leverage_intent="moderate",
    )


def test_two_critical_risks_apply_penalty():
    report = DevilsAdvocateReport(assessment="a", critical_risks=["r1", "r2"])
    out = apply_devils_advocate(_synthesis(0.70), report)
    assert out.confluence_score == pytest.approx(0.55)
    assert "r1" in out.top_risks and "r2" in out.top_risks
    assert "existing risk" in out.top_risks


def test_zero_risks_apply_boost():
    report = DevilsAdvocateReport(assessment="clean", critical_risks=[])
    out = apply_devils_advocate(_synthesis(0.70), report)
    assert out.confluence_score == pytest.approx(0.75)


def test_one_risk_no_change():
    report = DevilsAdvocateReport(assessment="a", critical_risks=["r1"])
    out = apply_devils_advocate(_synthesis(0.70), report)
    assert out.confluence_score == pytest.approx(0.70)


def test_confluence_clamped_to_one():
    report = DevilsAdvocateReport(assessment="clean", critical_risks=[])
    out = apply_devils_advocate(_synthesis(0.99), report)
    assert out.confluence_score == pytest.approx(1.0)


class _FakeService:
    def __init__(self, report: DevilsAdvocateReport) -> None:
        self._report = report
        self.calls: list[dict[str, object]] = []

    async def structured(self, **kwargs: object) -> DevilsAdvocateReport:
        self.calls.append(kwargs)
        return self._report


async def test_run_devils_advocate_passes_response_model():
    expected = DevilsAdvocateReport(assessment="a", critical_risks=["crowded trade"])
    service = _FakeService(expected)
    result = await run_devils_advocate(
        service,  # type: ignore[arg-type]
        "BTC/USDT:USDT",
        _synthesis(),
        _setup(),
        "- smart_money_divergence: diverges_bearish",
    )
    assert result is expected
    assert service.calls[0]["response_model"] is DevilsAdvocateReport
    assert service.calls[0]["entity_type"] == "devils_advocate"
    assert "diverges_bearish" in str(service.calls[0]["user"])
