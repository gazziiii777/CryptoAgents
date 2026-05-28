from datetime import datetime, timezone

import pytest

from core.settings import settings
from db.models import Decision, Direction, Signal
from db.research.writer import _build_agent_outputs, _build_signal_record
from tests.unit.test_persistence import _candidate_signal

_BAR = datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc)


def _signal() -> Signal:
    signal = Signal(
        symbol="ZEC/USDT:USDT",
        bar_close_ts=_BAR,
        direction=Direction.LONG,
        decision=Decision.TAKEN,
        decision_reason="taken",
    )
    signal.id = 42
    return signal


@pytest.mark.unit
def test_build_signal_record_maps_decision_and_setup() -> None:
    record = _build_signal_record(_candidate_signal(), _signal())
    assert record.trading_signal_id == 42
    assert record.decision == "taken"
    assert record.overall_bias == "Bullish"
    assert record.confluence_score == pytest.approx(settings.CONFIDENCE_SHRINKAGE)
    assert record.entry_price == 101.0
    assert record.risk_reward == 2.0
    assert record.direction == "long"


@pytest.mark.unit
def test_build_signal_record_captures_feature_snapshot() -> None:
    """P1: полный feature-snapshot из SignalDetails переносится в SignalRecord."""
    record = _build_signal_record(_candidate_signal(), _signal())
    # empty_signals() defaults — проверяем что поля присутствуют и берутся из signals
    assert record.volume_spike is False
    assert record.bb_squeeze is False
    assert record.near_swing is False
    assert record.liq_spike is False
    assert record.daily_trend == "neutral"
    assert record.funding_bias == "neutral"
    assert record.oi_weighted_funding_bias == "neutral"
    assert record.oi_change_4h_pct == pytest.approx(0.0)
    assert record.ema_cross is None
    assert record.rsi_divergence is None
    assert record.macd is None
    assert record.cvd_price_divergence is None


@pytest.mark.unit
def test_build_agent_outputs_one_row_per_analyst() -> None:
    outputs = _build_agent_outputs(_candidate_signal(), signal_record_id=7)
    names = {output.agent_name for output in outputs}
    assert names == {"macro", "derivatives", "sentiment", "technical"}
    technical = next(o for o in outputs if o.agent_name == "technical")
    assert technical.confidence == 0.6
    assert all(output.signal_record_id == 7 for output in outputs)
    assert all(output.score is not None for output in outputs)
