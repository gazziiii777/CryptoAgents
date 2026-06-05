from app.adapters.clients.binance.models import OISnapshot
from app.adapters.clients.ccxt.models import OHLCVCandle
from app.domain.indicators import calc_positioning_regime, calc_squeeze_setup


def _candles(start: float, end: float, n: int = 8) -> list[OHLCVCandle]:
    step = (end - start) / (n - 1)
    return [
        OHLCVCandle(
            timestamp=i,
            open=start + step * i,
            high=start + step * i,
            low=start + step * i,
            close=start + step * i,
            volume=1.0,
        )
        for i in range(n)
    ]


def _oi(start: float, end: float, n: int = 8) -> list[OISnapshot]:
    step = (end - start) / (n - 1)
    return [
        OISnapshot(
            timestamp=i,
            sumOpenInterest=start + step * i,
            sumOpenInterestValue=(start + step * i) * 100,
        )
        for i in range(n)
    ]


def test_price_up_oi_up_is_longs_building():
    assert (
        calc_positioning_regime(_candles(100, 110), _oi(1000, 1100)) == "longs_building"
    )


def test_price_down_oi_up_is_shorts_building():
    assert (
        calc_positioning_regime(_candles(110, 100), _oi(1000, 1100))
        == "shorts_building"
    )


def test_price_up_oi_down_is_shorts_covering():
    assert (
        calc_positioning_regime(_candles(100, 110), _oi(1100, 1000))
        == "shorts_covering"
    )


def test_price_down_oi_down_is_longs_unwinding():
    assert (
        calc_positioning_regime(_candles(110, 100), _oi(1100, 1000))
        == "longs_unwinding"
    )


def test_tiny_changes_are_neutral():
    assert (
        calc_positioning_regime(_candles(100.0, 100.05), _oi(1000.0, 1000.5))
        == "neutral"
    )


def test_squeeze_long_primed_when_longs_building_and_long_heavy():
    assert calc_squeeze_setup("longs_building", "long_heavy") == "long_squeeze_primed"


def test_squeeze_short_primed_when_shorts_building_and_short_heavy():
    assert (
        calc_squeeze_setup("shorts_building", "short_heavy") == "short_squeeze_primed"
    )


def test_no_squeeze_when_funding_neutral():
    assert calc_squeeze_setup("longs_building", "neutral") == "none"
    assert calc_squeeze_setup("shorts_covering", "long_heavy") == "none"
