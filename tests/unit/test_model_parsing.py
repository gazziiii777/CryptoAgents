from datetime import datetime, timezone

from app.clients.coinglass.models import LiquidationHeatmapData
from app.clients.lunarcrush.models import LunarCrushCoinMetrics, LunarCrushPost


def test_lunarcrush_metrics_coerces_string_numbers():
    m = LunarCrushCoinMetrics.model_validate({
        "symbol": "PEPE",
        "topic": "pepe",
        "galaxy_score": "68.5",
        "alt_rank": "42",
        "social_volume_24h": "15000",
        "categories": "memecoin, solana-ecosystem",
    })
    assert m.galaxy_score == 68.5
    assert m.alt_rank == 42
    assert m.social_volume_24h == 15000
    assert m.categories == ["memecoin", "solana-ecosystem"]


def test_lunarcrush_metrics_garbage_floats_become_none():
    m = LunarCrushCoinMetrics.model_validate({
        "symbol": "X",
        "galaxy_score": "n/a",
        "sentiment": None,
    })
    assert m.galaxy_score is None
    assert m.sentiment is None


def test_lunarcrush_metrics_missing_fields_use_defaults():
    m = LunarCrushCoinMetrics.model_validate({"symbol": "X"})
    assert m.categories == []
    assert m.alt_rank is None


def test_lunarcrush_post_int_zero_and_unix_datetime():
    created_ts = 1_700_000_000
    p = LunarCrushPost.model_validate({
        "id": "p1",
        "post_type": "tweet",
        "post_created": created_ts,
        "creator_followers": "500000",
    })
    assert p.creator_followers == 500_000
    assert p.interactions_24h == 0
    assert p.post_created == datetime.fromtimestamp(created_ts, tz=timezone.utc)


def test_lunarcrush_post_invalid_followers_default_zero():
    p = LunarCrushPost.model_validate({"creator_followers": "oops"})
    assert p.creator_followers == 0


def test_liquidation_heatmap_triplets_become_cells():
    data = LiquidationHeatmapData.model_validate({
        "y_axis": [100.0, 200.0],
        "liquidation_leverage_data": [[0, 1, 12345.0], [1, 0, 678.0]],
    })
    assert len(data.liquidation_leverage_data) == 2
    first = data.liquidation_leverage_data[0]
    assert first.x_idx == 0
    assert first.y_idx == 1
    assert first.amount_usd == 12345.0
