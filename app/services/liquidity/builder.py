from app.adapters.clients.ccxt.models import OHLCVCandle, OrderBook
from app.services.liquidity.imbalance import calc_book_imbalance
from app.services.liquidity.liquidation_model import estimate_liquidation_clusters
from app.services.liquidity.walls import detect_walls
from app.domain.models.liquidity import LiquidityLevel, LiquidityMap


def build_liquidity_map(
    symbol: str,
    mark_price: float,
    candles: list[OHLCVCandle],
    order_book: OrderBook | None,
) -> LiquidityMap:
    """Собирает карту ликвидности символа: стены из стакана + прокси-кластеры
    ликвидаций из volume profile свечей, плюс ближайшие магниты/стены к цене.

    order_book=None (фетч стакана упал) → карта без стен, только кластеры.
    """
    walls = detect_walls(order_book) if order_book is not None else []
    clusters = estimate_liquidation_clusters(candles, mark_price)
    return LiquidityMap(
        symbol=symbol,
        mark_price=mark_price,
        walls=walls,
        liq_clusters=clusters,
        book_imbalance=calc_book_imbalance(order_book),
        nearest_magnet_above=_nearest_above(clusters, mark_price),
        nearest_magnet_below=_nearest_below(clusters, mark_price),
        nearest_sell_wall_above=_nearest_above(
            [w for w in walls if w.kind == "sell_wall"], mark_price
        ),
        nearest_buy_wall_below=_nearest_below(
            [w for w in walls if w.kind == "buy_wall"], mark_price
        ),
    )


def _nearest_above(
    levels: list[LiquidityLevel], mark_price: float
) -> LiquidityLevel | None:
    above = [level for level in levels if level.price > mark_price]
    if not above:
        return None
    return min(above, key=lambda level: level.price - mark_price)


def _nearest_below(
    levels: list[LiquidityLevel], mark_price: float
) -> LiquidityLevel | None:
    below = [level for level in levels if level.price < mark_price]
    if not below:
        return None
    return min(below, key=lambda level: mark_price - level.price)
