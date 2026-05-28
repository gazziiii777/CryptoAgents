from datetime import datetime, timezone

import pytest

from app.scheduler import seconds_until_next_tick

_LAG = 60


@pytest.mark.unit
def test_mid_cycle_counts_to_next_boundary() -> None:
    now = datetime(2026, 1, 1, 2, 0, tzinfo=timezone.utc)
    assert seconds_until_next_tick(now) == 2 * 3600 + _LAG


@pytest.mark.unit
def test_on_boundary_waits_full_cycle() -> None:
    now = datetime(2026, 1, 1, 4, 0, tzinfo=timezone.utc)
    assert seconds_until_next_tick(now) == 4 * 3600 + _LAG


@pytest.mark.unit
def test_just_before_boundary() -> None:
    now = datetime(2026, 1, 1, 7, 59, 0, tzinfo=timezone.utc)
    assert seconds_until_next_tick(now) == 60 + _LAG
