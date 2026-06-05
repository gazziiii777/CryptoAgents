from app.adapters.clients.ccxt.models import OHLCVCandle
from app.domain.synthesis.levelcomputer import resolve_setup
from app.domain.models.setup import EntryReference, SetupIntent, StopReference, TargetReference


def _candles_4h(n: int = 40) -> list[OHLCVCandle]:
    return [
        OHLCVCandle(
            timestamp=i,
            open=100.0 + i * 0.05,
            high=100.0 + i * 0.05 + 0.3,
            low=100.0 + i * 0.05 - 0.3,
            close=100.0 + i * 0.05,
            volume=1000.0,
        )
        for i in range(n)
    ]


def _candles_1d(n: int = 5) -> list[OHLCVCandle]:
    return [
        OHLCVCandle(
            timestamp=i, open=100.0, high=103.0, low=98.0, close=101.0, volume=1.0
        )
        for i in range(n)
    ]


def _long_intent(**overrides: object) -> SetupIntent:
    base = {
        "reasoning": "uptrend pullback",
        "direction": "long",
        "setup_type": "trend_continuation",
        "entry": EntryReference(kind="swing_low_4h", lookback=20),
        "entry_offset_atr": 0.0,
        "stop": StopReference(kind="atr_distance", atr_multiplier=2.0),
        "stop_offset_atr": 0.5,
        "target": TargetReference(kind="swing_high_4h", lookback=20),
        "entry_trigger": "at_price",
        "valid_hours": 8,
        "leverage_intent": "moderate",
        "leverage_reasoning": "standard conviction",
    }
    base.update(overrides)
    return SetupIntent.model_validate(base)


_CURRENT_PRICE = 102.0


def test_resolve_long_setup_produces_ordered_prices():
    setup = resolve_setup(
        _long_intent(),
        _candles_4h(),
        _candles_1d(),
        current_price=_CURRENT_PRICE,
        funding_rate=0.0001,
    )
    assert setup is not None
    assert setup.stop_price < setup.entry_price < setup.target_price
    assert setup.risk_reward > 0
    assert setup.funding_impact_pct == 0.0001 * 8 / 8
    assert "below" in setup.invalidation


def test_atr_distance_target_is_ordered_and_controls_rr():
    setup = resolve_setup(
        _long_intent(
            entry=EntryReference(kind="prev_day_high"),
            stop=StopReference(kind="atr_distance", atr_multiplier=2.0),
            target=TargetReference(kind="atr_distance", atr_multiplier=3.0),
        ),
        _candles_4h(),
        _candles_1d(),
        current_price=_CURRENT_PRICE,
        funding_rate=0.0,
    )
    assert setup is not None
    assert setup.stop_price < setup.entry_price < setup.target_price
    assert round(setup.risk_reward, 2) == 1.5


def test_atr_stop_distance_is_clamped_to_cap():
    setup = resolve_setup(
        _long_intent(stop=StopReference(kind="atr_distance", atr_multiplier=50.0)),
        _candles_4h(),
        _candles_1d(),
        current_price=_CURRENT_PRICE,
        funding_rate=0.0,
    )
    assert setup is not None
    assert abs(setup.entry_price - setup.stop_price) / setup.entry_price <= 0.08 + 1e-9


def test_far_target_is_capped_to_max_distance():
    setup = resolve_setup(
        _long_intent(target=TargetReference(kind="atr_distance", atr_multiplier=100.0)),
        _candles_4h(),
        _candles_1d(),
        current_price=_CURRENT_PRICE,
        funding_rate=0.0,
    )
    assert setup is not None
    assert (
        abs(setup.target_price - setup.entry_price) / setup.entry_price <= 0.20 + 1e-9
    )
    assert setup.stop_price < setup.entry_price < setup.target_price


def test_rejects_when_swing_stop_too_far():
    far_day = [
        OHLCVCandle(
            timestamp=0, open=100.0, high=130.0, low=98.0, close=120.0, volume=1.0
        ),
        OHLCVCandle(
            timestamp=1, open=120.0, high=135.0, low=119.0, close=130.0, volume=1.0
        ),
    ]
    setup = resolve_setup(
        _long_intent(
            entry=EntryReference(kind="prev_day_high"),
            stop=StopReference(kind="swing_low_4h", lookback=20),
            stop_offset_atr=0.1,
            target=TargetReference(kind="atr_distance", atr_multiplier=2.0),
        ),
        _candles_4h(),
        far_day,
        current_price=130.0,
        funding_rate=0.0,
    )
    assert setup is None


def test_market_entry_uses_current_price():
    setup = resolve_setup(
        _long_intent(
            entry=EntryReference(kind="market"),
            target=TargetReference(kind="atr_distance", atr_multiplier=3.0),
        ),
        _candles_4h(),
        _candles_1d(),
        current_price=_CURRENT_PRICE,
        funding_rate=0.0,
    )
    assert setup is not None
    assert setup.entry_price == _CURRENT_PRICE
    assert setup.stop_price < setup.entry_price < setup.target_price


def test_limit_entry_executes_at_market():
    setup = resolve_setup(
        _long_intent(
            entry=EntryReference(kind="swing_low_4h", lookback=20),
            entry_offset_atr=-0.5,
            target=TargetReference(kind="atr_distance", atr_multiplier=3.0),
        ),
        _candles_4h(),
        _candles_1d(),
        current_price=_CURRENT_PRICE,
        funding_rate=0.0,
    )
    assert setup is not None
    assert setup.entry_price == _CURRENT_PRICE


def test_target_falls_back_when_anchor_on_wrong_side():
    setup = resolve_setup(
        _long_intent(target=TargetReference(kind="prev_day_low")),
        _candles_4h(),
        _candles_1d(),
        current_price=_CURRENT_PRICE,
        funding_rate=0.0,
    )
    assert setup is not None
    assert setup.stop_price < setup.entry_price < setup.target_price
    assert round(setup.risk_reward, 2) == 2.0
