from decimal import Decimal

import pytest

from app.portfolio.sizing import compute_qty, confidence_risk_pct

_GATE = 0.55
_MIN = Decimal("0.005")
_MAX = Decimal("0.02")


@pytest.mark.unit
def test_confidence_risk_min_at_gate() -> None:
    assert confidence_risk_pct(_GATE, _GATE, _MIN, _MAX) == _MIN


@pytest.mark.unit
def test_confidence_risk_max_at_full_confidence() -> None:
    assert confidence_risk_pct(1.0, _GATE, _MIN, _MAX) == _MAX


@pytest.mark.unit
def test_confidence_risk_can_exceed_one_percent() -> None:
    risk = confidence_risk_pct(0.85, _GATE, _MIN, _MAX)
    assert risk > Decimal("0.01")
    assert _MIN <= risk <= _MAX


@pytest.mark.unit
def test_compute_qty_fixed_risk() -> None:
    qty = compute_qty(Decimal("2000"), Decimal("100"), Decimal("95"), Decimal("0.01"))
    assert qty == Decimal("4")


@pytest.mark.unit
def test_compute_qty_uses_abs_distance_for_short() -> None:
    qty = compute_qty(Decimal("2000"), Decimal("100"), Decimal("105"), Decimal("0.01"))
    assert qty == Decimal("4")


@pytest.mark.unit
def test_compute_qty_zero_when_stop_equals_entry() -> None:
    qty = compute_qty(Decimal("2000"), Decimal("100"), Decimal("100"), Decimal("0.01"))
    assert qty == Decimal(0)
