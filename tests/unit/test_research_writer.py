from datetime import datetime, timezone

import pytest

from app.domain.models.screener import SignalDetails
from core.settings import settings
from db.models import Decision, Direction, Signal
from db.research.writer import _build_agent_outputs, _build_signal_record
from tests.fixtures.fx_signals import make_candidate_signal

_BAR = datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc)


def _distinct_signals() -> SignalDetails:
    """Snapshot с НЕ-дефолтными значениями — ловит реальный маппинг полей в SignalRecord."""
    return SignalDetails(
        atr=1.5,
        volume_spike=True,
        bb_squeeze=True,
        ema_cross="golden",
        rsi_level=71.0,
        rsi_divergence="bullish",
        macd="bullish",
        vwap_bias="above",
        daily_trend="up",
        near_swing=True,
        oi_change_4h_pct=0.12,
        oi_trend="growing",
        funding_rate=0.0008,
        funding_bias="long_heavy",
        oi_weighted_funding_bias="short_heavy",
        long_short_ratio=1.8,
        cvd_trend="rising",
        cvd_price_divergence="bearish",
        liq_spike=True,
        top_trader_ls_ratio=2.1,
        basis=0.0003,
        smart_money_divergence="diverges_bullish",
        positioning_regime="longs_building",
        squeeze_setup="long_squeeze_primed",
        spot_perp_divergence="bullish",
    )


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
    record = _build_signal_record(make_candidate_signal(), _signal())
    assert record.trading_signal_id == 42
    assert record.decision == "taken"
    assert record.overall_bias == "Bullish"
    assert record.confluence_score == pytest.approx(settings.CONFIDENCE_SHRINKAGE)
    assert record.entry_price == 101.0
    assert record.risk_reward == 2.0
    assert record.direction == "long"


@pytest.mark.unit
def test_build_signal_record_captures_feature_snapshot() -> None:
    """P1: feature-snapshot из SignalDetails переносится в SignalRecord без потерь."""
    record = _build_signal_record(
        make_candidate_signal(signals=_distinct_signals()), _signal()
    )
    assert record.volume_spike is True
    assert record.bb_squeeze is True
    assert record.near_swing is True
    assert record.liq_spike is True
    assert record.daily_trend == "up"
    assert record.funding_bias == "long_heavy"
    assert record.oi_weighted_funding_bias == "short_heavy"
    assert record.oi_change_4h_pct == pytest.approx(0.12)
    assert record.ema_cross == "golden"
    assert record.rsi_divergence == "bullish"
    assert record.macd == "bullish"
    assert record.cvd_price_divergence == "bearish"
    assert record.smart_money_divergence == "diverges_bullish"
    assert record.positioning_regime == "longs_building"
    assert record.squeeze_setup == "long_squeeze_primed"
    assert record.spot_perp_divergence == "bullish"
    assert record.book_imbalance is None


@pytest.mark.unit
def test_build_agent_outputs_one_row_per_analyst() -> None:
    outputs = _build_agent_outputs(make_candidate_signal(), signal_record_id=7)
    names = {output.agent_name for output in outputs}
    assert names == {"macro", "derivatives", "sentiment", "technical"}
    technical = next(o for o in outputs if o.agent_name == "technical")
    assert technical.confidence == 0.6
    assert all(output.signal_record_id == 7 for output in outputs)
    assert all(output.score is not None for output in outputs)
