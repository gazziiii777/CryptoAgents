from decimal import Decimal

import pytest

from app.portfolio.pnl import (
    entry_exit_fees,
    funding_cost,
    price_pnl,
    realized_pnl,
    unrealized_pnl,
)
from db.models import PositionSide


@pytest.mark.unit
def test_price_pnl_long_and_short() -> None:
    assert price_pnl(
        PositionSide.LONG, Decimal("100"), Decimal("110"), Decimal("2")
    ) == Decimal("20")
    assert price_pnl(
        PositionSide.SHORT, Decimal("100"), Decimal("90"), Decimal("2")
    ) == Decimal("20")


@pytest.mark.unit
def test_entry_exit_fees() -> None:
    fees = entry_exit_fees(
        Decimal("100"), Decimal("110"), Decimal("2"), Decimal("0.0005")
    )
    assert fees == Decimal("0.21")


@pytest.mark.unit
def test_funding_cost_long_pays_short_receives() -> None:
    long = funding_cost(
        PositionSide.LONG, Decimal("100"), Decimal("2"), Decimal("0.001"), 3
    )
    short = funding_cost(
        PositionSide.SHORT, Decimal("100"), Decimal("2"), Decimal("0.001"), 3
    )
    assert long == Decimal("0.6")
    assert short == Decimal("-0.6")


@pytest.mark.unit
def test_funding_cost_zero_cycles() -> None:
    assert funding_cost(
        PositionSide.LONG, Decimal("100"), Decimal("2"), Decimal("0.001"), 0
    ) == Decimal(0)


@pytest.mark.unit
def test_realized_pnl_combines_components() -> None:
    pnl = realized_pnl(
        PositionSide.LONG,
        Decimal("100"),
        Decimal("110"),
        Decimal("2"),
        Decimal("0.0005"),
        Decimal("0.001"),
        3,
    )
    assert pnl == Decimal("19.19")


@pytest.mark.unit
def test_unrealized_pnl() -> None:
    assert unrealized_pnl(
        PositionSide.LONG, Decimal("100"), Decimal("105"), Decimal("2")
    ) == Decimal("10")
