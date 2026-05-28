from decimal import Decimal

import pytest

from app.portfolio.models import PortfolioState


@pytest.mark.unit
def test_drawdown_pct() -> None:
    state = PortfolioState(
        equity=Decimal("1700"),
        peak_nav=Decimal("2000"),
        open_count=0,
        long_count=0,
        short_count=0,
    )
    assert state.drawdown_pct == Decimal("0.15")


@pytest.mark.unit
def test_drawdown_pct_zero_peak_is_safe() -> None:
    state = PortfolioState(
        equity=Decimal("0"),
        peak_nav=Decimal("0"),
        open_count=0,
        long_count=0,
        short_count=0,
    )
    assert state.drawdown_pct == Decimal(0)
