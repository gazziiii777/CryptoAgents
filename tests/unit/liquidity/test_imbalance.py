from app.adapters.clients.ccxt.models import OrderBook, OrderBookLevel
from app.services.liquidity.imbalance import calc_book_imbalance


def _book(bid_amt: float, ask_amt: float, n: int = 5) -> OrderBook:
    return OrderBook(
        bids=[OrderBookLevel(price=100 - i, amount=bid_amt) for i in range(n)],
        asks=[OrderBookLevel(price=101 + i, amount=ask_amt) for i in range(n)],
    )


def test_bid_heavy_is_positive():
    assert calc_book_imbalance(_book(10.0, 1.0)) > 0.5


def test_ask_heavy_is_negative():
    assert calc_book_imbalance(_book(1.0, 10.0)) < -0.5


def test_balanced_is_near_zero():
    assert calc_book_imbalance(_book(5.0, 5.0)) == 0.0


def test_none_book_is_zero():
    assert calc_book_imbalance(None) == 0.0


def test_empty_book_is_zero():
    assert calc_book_imbalance(OrderBook(bids=[], asks=[])) == 0.0
