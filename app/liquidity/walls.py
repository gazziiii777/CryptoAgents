from statistics import median

from app.clients.ccxt.models import OrderBook, OrderBookLevel
from app.models.liquidity import LiquidityKind, LiquidityLevel
from core.settings import settings


def detect_walls(order_book: OrderBook) -> list[LiquidityLevel]:
    return _side_walls(order_book.bids, "buy_wall") + _side_walls(
        order_book.asks, "sell_wall"
    )


def _side_walls(
    levels: list[OrderBookLevel], kind: LiquidityKind
) -> list[LiquidityLevel]:
    if len(levels) < settings.LIQUIDITY_WALL_MIN_LEVELS:
        return []
    baseline = median(level.amount for level in levels)
    if baseline <= 0:
        return []
    threshold = baseline * settings.LIQUIDITY_WALL_SIZE_MULT
    walls = [level for level in levels if level.amount >= threshold]
    if not walls:
        return []
    max_amount = max(level.amount for level in walls)
    return [
        LiquidityLevel(price=level.price, kind=kind, strength=level.amount / max_amount)
        for level in walls
    ]
