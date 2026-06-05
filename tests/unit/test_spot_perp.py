from app.adapters.clients.binance.models import CVDPoint
from app.domain.indicators import calc_spot_perp_divergence


def _cvd(values: list[float]) -> list[CVDPoint]:
    return [CVDPoint(timestamp=i, cvd=v) for i, v in enumerate(values)]


_RISING = [1.0, 2.0, 3.0, 4.0, 6.0, 9.0, 13.0, 18.0]
_FALLING = [18.0, 13.0, 9.0, 6.0, 4.0, 3.0, 2.0, 1.0]
_FLAT = [5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0]


def test_spot_rising_perp_not_rising_is_bullish():
    assert calc_spot_perp_divergence(_cvd(_RISING), _cvd(_FALLING)) == "bullish"
    assert calc_spot_perp_divergence(_cvd(_RISING), _cvd(_FLAT)) == "bullish"


def test_spot_falling_perp_not_falling_is_bearish():
    assert calc_spot_perp_divergence(_cvd(_FALLING), _cvd(_RISING)) == "bearish"
    assert calc_spot_perp_divergence(_cvd(_FALLING), _cvd(_FLAT)) == "bearish"


def test_agreement_is_none():
    assert calc_spot_perp_divergence(_cvd(_RISING), _cvd(_RISING)) == "none"
    assert calc_spot_perp_divergence(_cvd(_FALLING), _cvd(_FALLING)) == "none"


def test_no_spot_data_is_none():
    assert calc_spot_perp_divergence([], _cvd(_RISING)) == "none"
