from datetime import timezone

from app.clients.binance.liquidations import _parse
from app.clients.binance.models import ForcedLiquidation
from db.research.writer import _to_liquidation_row

_TRADE_TIME_MS = 1568014460893


def _message(side: str) -> dict[str, object]:
    return {
        "stream": "!forceOrder@arr",
        "data": {
            "e": "forceOrder",
            "E": 1,
            "o": {
                "s": "BTCUSDT",
                "S": side,
                "o": "LIMIT",
                "ap": "100.0",
                "z": "2.0",
                "T": _TRADE_TIME_MS,
            },
        },
    }


def test_parse_extracts_forced_liquidation():
    event = _parse(_message("SELL"))

    assert event is not None
    assert event.symbol == "BTCUSDT"
    assert event.order_side == "SELL"
    assert event.price == 100.0
    assert event.quantity == 2.0
    assert event.trade_time_ms == _TRADE_TIME_MS


def test_parse_returns_none_on_malformed_message():
    assert _parse({}) is None
    assert _parse({"data": {}}) is None
    assert _parse({"data": {"o": "not-a-dict"}}) is None


def test_sell_order_maps_to_long_liquidation():
    event = ForcedLiquidation(
        symbol="BTCUSDT",
        order_side="SELL",
        price=100.0,
        quantity=2.0,
        trade_time_ms=_TRADE_TIME_MS,
    )

    row = _to_liquidation_row(event)

    assert row.liquidated_side == "long"
    assert row.notional_usd == 200.0
    assert row.trade_ts.tzinfo == timezone.utc


def test_buy_order_maps_to_short_liquidation():
    event = ForcedLiquidation(
        symbol="BTCUSDT",
        order_side="BUY",
        price=50.0,
        quantity=3.0,
        trade_time_ms=_TRADE_TIME_MS,
    )

    row = _to_liquidation_row(event)

    assert row.liquidated_side == "short"
    assert row.notional_usd == 150.0
