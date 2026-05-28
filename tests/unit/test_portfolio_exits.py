from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.clients.ccxt.models import OHLCVCandle
from app.portfolio.exits import evaluate_candle_exit, funding_cycles, is_expired
from db.models import ExitReason, PositionSide

_TS = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _candle(high: float, low: float) -> OHLCVCandle:
    return OHLCVCandle(timestamp=0, open=low, high=high, low=low, close=low, volume=1.0)


@pytest.mark.unit
def test_long_stop_hit() -> None:
    outcome = evaluate_candle_exit(
        PositionSide.LONG, Decimal("95"), Decimal("110"), _candle(96, 94), _TS
    )
    assert outcome is not None
    assert outcome.reason == ExitReason.STOP
    assert outcome.price == Decimal("95")


@pytest.mark.unit
def test_long_target_hit() -> None:
    outcome = evaluate_candle_exit(
        PositionSide.LONG, Decimal("95"), Decimal("110"), _candle(111, 100), _TS
    )
    assert outcome is not None
    assert outcome.reason == ExitReason.TARGET
    assert outcome.price == Decimal("110")


@pytest.mark.unit
def test_long_both_hit_prefers_stop() -> None:
    outcome = evaluate_candle_exit(
        PositionSide.LONG, Decimal("95"), Decimal("110"), _candle(111, 94), _TS
    )
    assert outcome is not None
    assert outcome.reason == ExitReason.STOP


@pytest.mark.unit
def test_short_stop_and_target() -> None:
    stop = evaluate_candle_exit(
        PositionSide.SHORT, Decimal("105"), Decimal("90"), _candle(106, 100), _TS
    )
    target = evaluate_candle_exit(
        PositionSide.SHORT, Decimal("105"), Decimal("90"), _candle(100, 89), _TS
    )
    assert stop is not None and stop.reason == ExitReason.STOP
    assert target is not None and target.reason == ExitReason.TARGET


@pytest.mark.unit
def test_no_exit_returns_none() -> None:
    assert (
        evaluate_candle_exit(
            PositionSide.LONG, Decimal("95"), Decimal("110"), _candle(105, 100), _TS
        )
        is None
    )


@pytest.mark.unit
def test_short_no_exit_returns_none() -> None:
    assert (
        evaluate_candle_exit(
            PositionSide.SHORT, Decimal("105"), Decimal("90"), _candle(102, 95), _TS
        )
        is None
    )


@pytest.mark.unit
def test_is_expired() -> None:
    assert is_expired(_TS, 8, _TS + timedelta(hours=8))
    assert not is_expired(_TS, 8, _TS + timedelta(hours=7))


@pytest.mark.unit
def test_funding_cycles() -> None:
    entry = datetime(2026, 1, 1, 7, tzinfo=timezone.utc)
    assert funding_cycles(entry, datetime(2026, 1, 1, 9, tzinfo=timezone.utc)) == 1
    assert funding_cycles(entry, datetime(2026, 1, 1, 17, tzinfo=timezone.utc)) == 2
    assert funding_cycles(entry, entry) == 0
