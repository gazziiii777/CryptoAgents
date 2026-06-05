from app.adapters.clients.coinglass.models import OIAggregatedCandle
from app.domain.indicators import calc_aggregated_oi_trend


def _candles(values: list[float]) -> list[OIAggregatedCandle]:
    return [
        OIAggregatedCandle(time=i, open=v, high=v, low=v, close=v)
        for i, v in enumerate(values)
    ]


def test_growing_when_aggregated_oi_rises_above_threshold():
    # +20% over the lookback window (>OI_TREND_MIN_PCT=0.15)
    assert calc_aggregated_oi_trend(_candles([100.0] * 5 + [120.0] * 6)) == "growing"


def test_shrinking_when_aggregated_oi_falls_below_threshold():
    assert calc_aggregated_oi_trend(_candles([120.0] * 5 + [100.0] * 6)) == "shrinking"


def test_neutral_when_change_small():
    assert calc_aggregated_oi_trend(_candles([100.0] * 11)) == "neutral"


def test_neutral_when_insufficient_candles():
    assert calc_aggregated_oi_trend(_candles([100.0, 130.0])) == "neutral"


def test_neutral_when_empty():
    assert calc_aggregated_oi_trend([]) == "neutral"
