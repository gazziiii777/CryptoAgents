from app.adapters.clients.ccxt.models import OrderBook, OrderBookLevel
from app.services.liquidity.walls import detect_walls


def _book(
    bids: list[tuple[float, float]], asks: list[tuple[float, float]]
) -> OrderBook:
    return OrderBook(
        bids=[OrderBookLevel(price=p, amount=a) for p, a in bids],
        asks=[OrderBookLevel(price=p, amount=a) for p, a in asks],
    )


def _flat_side(
    start: float, amount: float, step: float, count: int
) -> list[tuple[float, float]]:
    return [(start + step * i, amount) for i in range(count)]


def test_detects_buy_and_sell_walls():
    bids = _flat_side(100.0, 1.0, -1.0, 12)
    bids[3] = (97.0, 50.0)
    asks = _flat_side(101.0, 1.0, 1.0, 12)
    asks[5] = (106.0, 80.0)

    walls = detect_walls(_book(bids, asks))
    kinds = {w.kind for w in walls}

    assert "buy_wall" in kinds
    assert "sell_wall" in kinds
    assert any(w.price == 97.0 for w in walls if w.kind == "buy_wall")
    assert any(w.price == 106.0 for w in walls if w.kind == "sell_wall")


def test_no_walls_when_book_is_flat():
    bids = _flat_side(100.0, 1.0, -1.0, 12)
    asks = _flat_side(101.0, 1.0, 1.0, 12)

    assert detect_walls(_book(bids, asks)) == []


def test_skips_side_with_too_few_levels():
    bids = [(100.0, 1.0), (99.0, 99.0)]
    asks = _flat_side(101.0, 1.0, 1.0, 12)

    walls = detect_walls(_book(bids, asks))

    assert all(w.kind != "buy_wall" for w in walls)


def test_wall_strength_is_normalized_to_one():
    asks = _flat_side(101.0, 1.0, 1.0, 12)
    asks[5] = (106.0, 80.0)

    walls = detect_walls(_book([], asks))
    sell_walls = [w for w in walls if w.kind == "sell_wall"]

    assert sell_walls
    assert max(w.strength for w in sell_walls) == 1.0
