from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PortfolioState:
    """Снимок портфеля для pre-trade проверок PortfolioManager."""

    equity: Decimal
    peak_nav: Decimal
    open_count: int
    long_count: int
    short_count: int

    @property
    def drawdown_pct(self) -> Decimal:
        if self.peak_nav <= 0:
            return Decimal(0)
        return (self.peak_nav - self.equity) / self.peak_nav
