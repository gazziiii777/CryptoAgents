from decimal import Decimal

from db.models import PositionSide


def _side_sign(side: PositionSide) -> Decimal:
    return Decimal(1) if side == PositionSide.LONG else Decimal(-1)


def price_pnl(
    side: PositionSide, entry_price: Decimal, exit_price: Decimal, qty: Decimal
) -> Decimal:
    """Ценовой PnL без издержек. Long: (exit − entry)×qty; short: зеркально."""
    return (exit_price - entry_price) * qty * _side_sign(side)


def entry_exit_fees(
    entry_price: Decimal, exit_price: Decimal, qty: Decimal, fee_rate: Decimal
) -> Decimal:
    """Taker-комиссия на вход и выход: (notional_in + notional_out) × fee_rate."""
    return (entry_price * qty + exit_price * qty) * fee_rate


def funding_cost(
    side: PositionSide,
    entry_price: Decimal,
    qty: Decimal,
    funding_rate: Decimal,
    cycles: int,
) -> Decimal:
    """Стоимость фандинга за удержание (положительная = расход).

    Аппроксимация MVP: ставка постоянна, ноционал по цене входа, начисление по числу
    пройденных 8h-циклов. Long при положительной ставке платит, short — получает.
    """
    if cycles <= 0:
        return Decimal(0)
    notional = entry_price * qty
    return notional * funding_rate * Decimal(cycles) * _side_sign(side)


def realized_pnl(
    side: PositionSide,
    entry_price: Decimal,
    exit_price: Decimal,
    qty: Decimal,
    fee_rate: Decimal,
    funding_rate: Decimal,
    cycles: int,
) -> Decimal:
    """Итоговый PnL: ценовой минус комиссии минус фандинг."""
    return (
        price_pnl(side, entry_price, exit_price, qty)
        - entry_exit_fees(entry_price, exit_price, qty, fee_rate)
        - funding_cost(side, entry_price, qty, funding_rate, cycles)
    )


def unrealized_pnl(
    side: PositionSide, entry_price: Decimal, mark_price: Decimal, qty: Decimal
) -> Decimal:
    """Нереализованный PnL по текущей цене (mark-to-market, без издержек)."""
    return price_pnl(side, entry_price, mark_price, qty)
