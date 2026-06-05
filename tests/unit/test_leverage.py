import pytest

from app.domain.risk.leverage import compute_leverage

_CAP = 10


@pytest.mark.parametrize(
    "setup_type, intent, expected",
    [
        ("trend_continuation", "conservative", 3),
        ("trend_continuation", "moderate", 5),
        ("trend_continuation", "aggressive", 8),
        ("breakout", "aggressive", 7),
        ("reversal", "conservative", 2),
        ("reversal", "aggressive", 5),
    ],
)
def test_compute_leverage_table(setup_type, intent, expected):
    assert compute_leverage(setup_type, intent, _CAP) == expected


def test_unknown_pair_falls_back_to_conservative_default():
    assert compute_leverage("unknown", "moderate", _CAP) == 3
    assert compute_leverage("trend_continuation", "reckless", _CAP) == 3


def test_capped_by_max_leverage():
    assert compute_leverage("trend_continuation", "aggressive", 4) == 4


def test_floor_is_one():
    assert compute_leverage("reversal", "conservative", 1) == 1
