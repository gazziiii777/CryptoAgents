from app.adapters.clients.ccxt.models import OHLCVCandle, OrderBook, OrderBookLevel
from app.services.liquidity.builder import build_liquidity_map


def _candle(typical: float, volume: float) -> OHLCVCandle:
    return OHLCVCandle(
        timestamp=0,
        open=typical,
        high=typical + 0.1,
        low=typical - 0.1,
        close=typical,
        volume=volume,
    )


def _candles() -> list[OHLCVCandle]:
    baseline = [_candle(95.0 + i * 0.25, 1.0) for i in range(41)]
    heavy = [_candle(100.0, 500.0) for _ in range(5)]
    return baseline + heavy


def _book_with_sell_wall() -> OrderBook:
    bids = [OrderBookLevel(price=100.0 - i, amount=1.0) for i in range(12)]
    asks = [OrderBookLevel(price=101.0 + i, amount=1.0) for i in range(12)]
    asks[4] = OrderBookLevel(price=105.0, amount=80.0)
    return OrderBook(bids=bids, asks=asks)


def test_map_without_order_book_has_no_walls():
    liquidity_map = build_liquidity_map("X/USDT:USDT", 100.0, _candles(), None)

    assert liquidity_map.walls == []
    assert liquidity_map.liq_clusters


def test_nearest_magnets_are_on_correct_side():
    liquidity_map = build_liquidity_map("X/USDT:USDT", 100.0, _candles(), None)

    above = liquidity_map.nearest_magnet_above
    below = liquidity_map.nearest_magnet_below
    assert above is None or above.price > 100.0
    assert below is None or below.price < 100.0


def test_order_book_populates_walls_and_nearest_sell_wall():
    liquidity_map = build_liquidity_map(
        "X/USDT:USDT", 100.0, _candles(), _book_with_sell_wall()
    )

    assert liquidity_map.walls
    assert liquidity_map.nearest_sell_wall_above is not None
    assert liquidity_map.nearest_sell_wall_above.price == 105.0
