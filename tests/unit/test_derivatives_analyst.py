import pytest

from app.analysts.derivatives import (
    _render_user_prompt,
    analyze_derivatives,
    classify_funding_squeeze_risk,
)
from app.models.analysis import DerivativesReport
from core.prompts.loader import load_prompt
from app.models.screener import empty_signals


@pytest.mark.parametrize(
    "funding_rate, expected",
    [
        (0.0040, "high"),
        (-0.0035, "high"),
        (0.0030, "high"),
        (0.0020, "moderate"),
        (-0.0016, "moderate"),
        (0.0005, "none"),
        (-0.0010, "none"),
        (0.0, "none"),
    ],
)
def test_funding_squeeze_risk_thresholds(funding_rate, expected):
    assert classify_funding_squeeze_risk(funding_rate) == expected


def test_render_includes_funding_squeeze_risk():
    template = load_prompt("derivatives").user
    signals = empty_signals().model_copy(update={"funding_rate": 0.0050})
    prompt = _render_user_prompt(template, signals)
    assert "Funding squeeze risk: high" in prompt


class _FakeService:
    def __init__(self, report: DerivativesReport) -> None:
        self._report = report
        self.calls: list[dict[str, object]] = []

    async def structured(self, **kwargs: object) -> DerivativesReport:
        self.calls.append(kwargs)
        return self._report


def test_render_formats_values_and_handles_none():
    template = load_prompt("derivatives").user
    signals = empty_signals().model_copy(
        update={
            "funding_rate": -0.00010607,
            "long_short_ratio": 0.50,
            "cvd_trend": "rising",
            "basis": None,
        }
    )
    prompt = _render_user_prompt(template, signals)
    assert "-0.00011" in prompt
    assert "0.50" in prompt
    assert "rising" in prompt
    assert "Basis: n/a" in prompt


async def test_analyze_derivatives_passes_response_model():
    expected = DerivativesReport(
        key_insight="balanced",
        funding_signal="Neutral",
        oi_signal="Neutral",
        ls_signal="Balanced",
        liq_nearest_long=None,
        liq_nearest_short=None,
        cvd_direction="Neutral",
        overall_bias="Neutral",
    )
    service = _FakeService(expected)

    result = await analyze_derivatives(service, empty_signals())  # type: ignore[arg-type]

    assert result is expected
    assert service.calls[0]["response_model"] is DerivativesReport
    assert service.calls[0]["entity_type"] == "derivatives"
