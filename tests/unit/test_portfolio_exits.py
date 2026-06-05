from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.clients.ccxt.models import OHLCVCandle
from app.portfolio.exits import (
    current_managed_stop,
    evaluate_candle_exit,
    funding_cycles,
    is_expired,
    walk_managed_exit,
)
from db.models import ExitReason, PositionSide

_TS = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _candle(high: float, low: float) -> OHLCVCandle:
    return OHLCVCandle(timestamp=0, open=low, high=high, low=low, close=low, volume=1.0)


def _c(idx: int, high: float, low: float) -> OHLCVCandle:
    ts_ms = int((_TS.timestamp() + (idx + 1) * 4 * 3600) * 1000)
    return OHLCVCandle(
        timestamp=ts_ms, open=low, high=high, low=low, close=low, volume=1.0
    )


def _walk_long(candles: list[OHLCVCandle]):
    return walk_managed_exit(
        PositionSide.LONG,
        Decimal("100"),
        Decimal("95"),
        Decimal("130"),
        candles,
        _TS,
        1.0,
        1.5,
        1.0,
    )


@pytest.mark.unit
def test_managed_breakeven_after_1r() -> None:
    # +1R (105) reached, then pulls back to entry → exit at breakeven (100)
    outcome, mfe = _walk_long([_c(0, 105, 101), _c(1, 102, 99)])
    assert outcome is not None
    assert outcome.reason == ExitReason.BREAKEVEN
    assert outcome.price == Decimal("100")
    assert mfe == pytest.approx(1.0)


@pytest.mark.unit
def test_managed_trailing_locks_profit() -> None:
    # runs to +2R (110), pulls back → trail exit at 110-1R = 105
    outcome, mfe = _walk_long([_c(0, 110, 101), _c(1, 106, 104)])
    assert outcome is not None
    assert outcome.reason == ExitReason.TRAILING_STOP
    assert outcome.price == Decimal("105")
    assert mfe == pytest.approx(2.0)


@pytest.mark.unit
def test_managed_plain_stop_unchanged() -> None:
    # drops to initial stop before any trigger → reason stays STOP
    outcome, mfe = _walk_long([_c(0, 99, 94)])
    assert outcome is not None
    assert outcome.reason == ExitReason.STOP
    assert outcome.price == Decimal("95")
    assert mfe == pytest.approx(0.0)


@pytest.mark.unit
def test_managed_target_still_wins() -> None:
    outcome, _ = _walk_long([_c(0, 131, 101)])
    assert outcome is not None
    assert outcome.reason == ExitReason.TARGET
    assert outcome.price == Decimal("130")


def _walk_short(candles: list[OHLCVCandle]):
    return walk_managed_exit(
        PositionSide.SHORT,
        Decimal("100"),
        Decimal("105"),
        Decimal("70"),
        candles,
        _TS,
        1.0,
        1.5,
        1.0,
    )


@pytest.mark.unit
def test_managed_short_breakeven() -> None:
    # short: -1R (95) reached, then pulls back up to entry → breakeven exit at 100
    outcome, mfe = _walk_short([_c(0, 99, 95), _c(1, 101, 98)])
    assert outcome is not None
    assert outcome.reason == ExitReason.BREAKEVEN
    assert outcome.price == Decimal("100")
    assert mfe == pytest.approx(1.0)


@pytest.mark.unit
def test_managed_short_trailing_locks_profit() -> None:
    # short runs to -2R (90), pulls back → trail exit at 90+1R = 95
    outcome, mfe = _walk_short([_c(0, 99, 90), _c(1, 96, 94)])
    assert outcome is not None
    assert outcome.reason == ExitReason.TRAILING_STOP
    assert outcome.price == Decimal("95")
    assert mfe == pytest.approx(2.0)


@pytest.mark.unit
def test_managed_short_plain_stop() -> None:
    outcome, mfe = _walk_short([_c(0, 106, 101)])
    assert outcome is not None
    assert outcome.reason == ExitReason.STOP
    assert outcome.price == Decimal("105")
    assert mfe == pytest.approx(0.0)


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


def _state_long(candles: list[OHLCVCandle]) -> tuple[Decimal, ExitReason]:
    return current_managed_stop(
        PositionSide.LONG, Decimal("100"), Decimal("95"), candles, _TS, 1.0, 1.5, 1.0
    )


@pytest.mark.unit
def test_current_stop_stays_initial_below_breakeven() -> None:
    stop, reason = _state_long([_c(0, 102, 101)])  # peak +0.4R < 1.0
    assert reason == ExitReason.STOP
    assert stop == Decimal("95")


@pytest.mark.unit
def test_current_stop_breakeven_after_1r() -> None:
    stop, reason = _state_long([_c(0, 105, 101)])  # +1R
    assert reason == ExitReason.BREAKEVEN
    assert stop == Decimal("100")


@pytest.mark.unit
def test_current_stop_trailing_after_activation() -> None:
    stop, reason = _state_long([_c(0, 110, 101)])  # +2R, trail dist 1R -> 110-5
    assert reason == ExitReason.TRAILING_STOP
    assert stop == Decimal("105")
