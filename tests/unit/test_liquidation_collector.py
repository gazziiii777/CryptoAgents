from datetime import timezone

from app.clients.binance.liquidations import _parse as parse_binance
from app.clients.bybit.liquidations import _parse as parse_bybit
from app.clients.okx.liquidations import _parse as parse_okx
from app.models.liquidations import NormalizedLiquidation
from db.research.writer import _to_liquidation_row

_TRADE_TIME_MS = 1568014460893


def _binance_message(side: str) -> dict[str, object]:
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


def test_binance_parse_maps_sell_to_long_liquidation():
    event = parse_binance(_binance_message("SELL"))

    assert event is not None
    assert event.exchange == "binance"
    assert event.symbol == "BTCUSDT"
    assert event.liquidated_side == "long"
    assert event.price == 100.0
    assert event.quantity == 2.0


def test_binance_parse_maps_buy_to_short_liquidation():
    event = parse_binance(_binance_message("BUY"))

    assert event is not None
    assert event.liquidated_side == "short"


def test_binance_parse_returns_none_on_malformed_message():
    assert parse_binance({}) is None
    assert parse_binance({"data": {}}) is None
    assert parse_binance({"data": {"o": "not-a-dict"}}) is None


def _okx_raw(pos_side: str) -> str:
    return (
        '{"arg":{"channel":"liquidation-orders"},"data":[{"instId":"BTC-USDT-SWAP",'
        '"details":[{"posSide":"' + pos_side + '","side":"sell","sz":"3.0",'
        '"bkPx":"50.0","ts":"' + str(_TRADE_TIME_MS) + '"}]}]}'
    )


def test_okx_parse_uses_pos_side_directly():
    events = parse_okx(_okx_raw("long"), {})

    assert len(events) == 1
    assert events[0].exchange == "okx"
    assert events[0].symbol == "BTC-USDT-SWAP"
    assert events[0].liquidated_side == "long"
    assert events[0].price == 50.0
    assert events[0].quantity == 3.0


def test_okx_applies_contract_size_to_quantity():
    events = parse_okx(_okx_raw("long"), {"BTC-USDT-SWAP": 0.01})

    assert events[0].quantity == 0.03


def test_okx_parse_ignores_pong_and_acks():
    assert parse_okx("pong", {}) == []
    assert parse_okx('{"event":"subscribe","arg":{}}', {}) == []


def _bybit_raw(position_side: str) -> str:
    return (
        '{"topic":"allLiquidation.BTCUSDT","type":"snapshot","ts":1,"data":'
        '[{"T":' + str(_TRADE_TIME_MS) + ',"s":"BTCUSDT","S":"' + position_side + '",'
        '"v":"2.0","p":"100.0"}]}'
    )


def test_bybit_buy_is_long_liquidation():
    events = parse_bybit(_bybit_raw("Buy"))

    assert len(events) == 1
    assert events[0].exchange == "bybit"
    assert events[0].liquidated_side == "long"
    assert events[0].price == 100.0


def test_bybit_sell_is_short_liquidation():
    events = parse_bybit(_bybit_raw("Sell"))

    assert events[0].liquidated_side == "short"


def test_bybit_parse_ignores_non_liquidation_topics():
    assert parse_bybit('{"op":"subscribe","success":true}') == []
    assert parse_bybit('{"topic":"orderbook.1.BTCUSDT","data":{}}') == []


def test_to_row_carries_exchange_and_notional():
    event = NormalizedLiquidation(
        exchange="okx",
        symbol="BTC-USDT-SWAP",
        order_side="sell",
        liquidated_side="long",
        price=50.0,
        quantity=3.0,
        trade_time_ms=_TRADE_TIME_MS,
    )

    row = _to_liquidation_row(event)

    assert row.exchange == "okx"
    assert row.liquidated_side == "long"
    assert row.notional_usd == 150.0
    assert row.trade_ts.tzinfo == timezone.utc
