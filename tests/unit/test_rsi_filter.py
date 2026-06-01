import pytest

from app.pipeline.analysis import _rsi_extreme_blocks


@pytest.mark.unit
def test_short_into_oversold_blocked() -> None:
    assert _rsi_extreme_blocks("short", 20.0) is True


@pytest.mark.unit
def test_short_normal_rsi_allowed() -> None:
    assert _rsi_extreme_blocks("short", 40.0) is False


@pytest.mark.unit
def test_long_into_overbought_blocked() -> None:
    assert _rsi_extreme_blocks("long", 80.0) is True


@pytest.mark.unit
def test_long_normal_rsi_allowed() -> None:
    assert _rsi_extreme_blocks("long", 60.0) is False


@pytest.mark.unit
def test_none_rsi_never_blocks() -> None:
    assert _rsi_extreme_blocks("short", None) is False
    assert _rsi_extreme_blocks("long", None) is False
