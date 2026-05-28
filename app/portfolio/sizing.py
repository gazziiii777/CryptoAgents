from decimal import Decimal


def confidence_risk_pct(
    confluence: float, gate: float, min_pct: Decimal, max_pct: Decimal
) -> Decimal:
    """Риск на сделку, растущий с уверенностью: min_pct при confluence=gate, max_pct при 1.0.

    Линейная интерполяция по «убеждённости» (confluence над гейтом). Так высокая
    согласованность аналитиков даёт бóльшую ставку (Kelly-подобно), а у гейта — минимум.
    """
    span = 1.0 - gate
    if span <= 0:
        return max_pct
    conviction = max(0.0, min(1.0, (confluence - gate) / span))
    return min_pct + Decimal(str(conviction)) * (max_pct - min_pct)


def compute_qty(
    nav: Decimal, entry_price: Decimal, stop_price: Decimal, risk_pct: Decimal
) -> Decimal:
    """Размер позиции из фиксированного риска: qty = (NAV × risk_pct) / |entry − stop|.

    Риск на сделку фиксирован (1% NAV в MVP). 0, если стоп совпадает с входом — такой
    сетап до сайзинга доходить не должен (LevelComputer его отсекает).
    """
    risk_per_unit = abs(entry_price - stop_price)
    if risk_per_unit <= 0:
        return Decimal(0)
    return (nav * risk_pct) / risk_per_unit
