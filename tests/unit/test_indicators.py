from app.clients.ccxt.models import OHLCVCandle
from app.screener.indicators import (
    calc_adx,
    calc_atr,
    calc_macd,
    calc_rsi_level,
    calc_volume_spike,
)


def _flat_candles(
    n: int, *, price: float = 100.0, volume: float = 100.0
) -> list[OHLCVCandle]:
    return [
        OHLCVCandle(
            timestamp=i, open=price, high=price, low=price, close=price, volume=volume
        )
        for i in range(n)
    ]


def test_calc_adx_insufficient_candles_returns_zero():
    assert calc_adx(_flat_candles(10)) == 0.0


def test_calc_atr_insufficient_candles_returns_zero():
    assert calc_atr(_flat_candles(5)) == 0.0


def test_calc_atr_flat_candles_is_zero():
    assert calc_atr(_flat_candles(30)) == 0.0


def test_calc_rsi_level_insufficient_returns_none():
    assert calc_rsi_level(_flat_candles(5)) is None


def test_calc_macd_insufficient_returns_none():
    assert calc_macd(_flat_candles(10)) is None


def test_calc_volume_spike_insufficient_returns_false():
    assert calc_volume_spike(_flat_candles(5)) is False


def test_calc_volume_spike_flat_volume_no_spike():
    assert calc_volume_spike(_flat_candles(25, volume=100.0)) is False


def test_calc_volume_spike_detects_last_bar_surge():
    candles = _flat_candles(24, volume=100.0)
    surge = OHLCVCandle(
        timestamp=99, open=100, high=100, low=100, close=100, volume=1000.0
    )
    assert calc_volume_spike([*candles, surge]) is True
