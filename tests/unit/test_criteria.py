from app.domain.models.screener import empty_signals
from app.services.screener.criteria import compute_direction, compute_score


def test_empty_signals_score_zero_direction_mixed():
    sig = empty_signals()
    assert compute_score(sig) == 0
    assert compute_direction(sig) == "mixed"


def test_direction_long_when_bullish_votes_reach_threshold():
    sig = empty_signals().model_copy(
        update={"ema_cross": "golden", "macd": "bullish", "daily_trend": "up"}
    )
    assert compute_direction(sig) == "long"


def test_direction_short_when_bearish_votes_reach_threshold():
    sig = empty_signals().model_copy(
        update={"ema_cross": "death", "macd": "bearish", "daily_trend": "down"}
    )
    assert compute_direction(sig) == "short"


def test_direction_mixed_below_threshold():
    sig = empty_signals().model_copy(update={"ema_cross": "golden", "macd": "bullish"})
    assert compute_direction(sig) == "mixed"


def test_retail_ls_ratio_is_contrarian():
    sig = empty_signals().model_copy(
        update={"ema_cross": "golden", "macd": "bullish", "long_short_ratio": 5.0}
    )
    assert compute_direction(sig) == "mixed"


def test_score_counts_activity_flags():
    sig = empty_signals().model_copy(
        update={"volume_spike": True, "bb_squeeze": True, "near_swing": True}
    )
    assert compute_score(sig) == 3


def test_score_counts_rsi_extreme():
    base = empty_signals()
    assert compute_score(base.model_copy(update={"rsi_level": 75.0})) == 1
    assert compute_score(base.model_copy(update={"rsi_level": 25.0})) == 1
    assert compute_score(base.model_copy(update={"rsi_level": 50.0})) == 0


def test_score_trend_vwap_alignment():
    sig = empty_signals().model_copy(update={"daily_trend": "up", "vwap_bias": "above"})
    assert compute_score(sig) == 1
    misaligned = empty_signals().model_copy(
        update={"daily_trend": "up", "vwap_bias": "below"}
    )
    assert compute_score(misaligned) == 0
