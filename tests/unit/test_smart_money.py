import pytest

from app.enricher.insight import classify_pump_risk
from app.screener.criteria import classify_smart_money_divergence

_HIGH = 3.3
_LOW = 0.55


@pytest.mark.parametrize(
    "retail, top, expected",
    [
        (3.5, 0.8, "diverges_bearish"),
        (0.5, 1.4, "diverges_bullish"),
        (3.5, 1.4, "confirms"),
        (0.5, 0.8, "confirms"),
        (1.5, 1.2, "neutral"),
        (None, 1.2, "neutral"),
        (3.5, None, "neutral"),
        (3.5, 1.0, "neutral"),
    ],
)
def test_smart_money_divergence(retail, top, expected):
    assert classify_smart_money_divergence(retail, top, _HIGH, _LOW) == expected


@pytest.mark.parametrize(
    "attention, influencers, news, expected",
    [
        ("spike", 5, 0, "high"),
        ("spike", 3, 0, "high"),
        ("spike", 2, 0, "moderate"),
        ("spike", 5, 2, "moderate"),
        ("normal", 5, 0, "none"),
        ("silent", 10, 0, "none"),
    ],
)
def test_pump_risk(attention, influencers, news, expected):
    assert classify_pump_risk(attention, influencers, news, 3) == expected
