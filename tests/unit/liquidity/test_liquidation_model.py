from app.clients.ccxt.models import OHLCVCandle
from app.liquidity.liquidation_model import estimate_liquidation_clusters


def _candle(typical: float, volume: float) -> OHLCVCandle:
    return OHLCVCandle(
        timestamp=0,
        open=typical,
        high=typical + 0.1,
        low=typical - 0.1,
        close=typical,
        volume=volume,
    )


def _spread_with_node(node_price: float, node_volume: float) -> list[OHLCVCandle]:
    baseline = [_candle(95.0 + i * 0.25, 1.0) for i in range(41)]
    heavy = [_candle(node_price, node_volume) for _ in range(5)]
    return baseline + heavy


def test_clusters_split_above_and_below_mark():
    candles = _spread_with_node(100.0, 500.0)

    clusters = estimate_liquidation_clusters(candles, mark_price=100.0)

    assert clusters
    assert any(c.kind == "long_liq_cluster" and c.price < 100.0 for c in clusters)
    assert any(c.kind == "short_liq_cluster" and c.price > 100.0 for c in clusters)


def test_strength_normalized_to_one():
    candles = _spread_with_node(100.0, 500.0)

    clusters = estimate_liquidation_clusters(candles, mark_price=100.0)

    assert max(c.strength for c in clusters) == 1.0


def test_kind_reflects_source_not_mark_position():
    candles = _spread_with_node(200.0, 500.0)

    clusters = estimate_liquidation_clusters(candles, mark_price=100.0)

    long_above_mark = [
        c for c in clusters if c.kind == "long_liq_cluster" and c.price > 100.0
    ]
    assert long_above_mark


def test_empty_candles_yield_no_clusters():
    assert estimate_liquidation_clusters([], mark_price=100.0) == []


def test_non_positive_mark_yields_no_clusters():
    candles = _spread_with_node(100.0, 500.0)

    assert estimate_liquidation_clusters(candles, mark_price=0.0) == []
