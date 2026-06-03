from app.clients.ccxt.models import OrderBook
from core.settings import settings


def calc_book_imbalance(
    order_book: OrderBook | None, depth: int = settings.LIQUIDITY_IMBALANCE_DEPTH
) -> float:
    """Дисбаланс стакана по top-depth уровням: (Σbid − Σask)/(Σbid + Σask), −1..+1.

    >0 — перевес покупателей (давление/поддержка вверх), <0 — продавцов. Пустой
    стакан или None → 0.0.
    """
    if order_book is None:
        return 0.0
    bid_volume = sum(level.amount for level in order_book.bids[:depth])
    ask_volume = sum(level.amount for level in order_book.asks[:depth])
    total = bid_volume + ask_volume
    if total == 0:
        return 0.0
    return (bid_volume - ask_volume) / total
