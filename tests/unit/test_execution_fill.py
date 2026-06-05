from app.adapters.clients.ccxt.models import OHLCVCandle
from app.services.entry.fill import evaluate_fill
from app.domain.models.setup import (
    EntryReference,
    FinalSignal,
    SetupIntent,
    StopReference,
    TargetReference,
)
from core.constants.decisions import (
    REASON_ENTRY_DRIFT,
    REASON_SIGNAL_READY,
    REASON_STALE_LEVELS,
)


def _candles(
    n: int, *, base: float = 100.0, last_close: float | None = None, hl: float = 0.5
) -> list[OHLCVCandle]:
    candles: list[OHLCVCandle] = []
    for i in range(n):
        close = last_close if (i == n - 1 and last_close is not None) else base
        candles.append(
            OHLCVCandle(
                timestamp=i,
                open=base,
                high=base + hl,
                low=base - hl,
                close=close,
                volume=100.0,
            )
        )
    return candles


def _intent() -> SetupIntent:
    return SetupIntent(
        reasoning="trend up",
        direction="long",
        setup_type="trend_continuation",
        entry=EntryReference(kind="market"),
        entry_offset_atr=0.0,
        stop=StopReference(kind="atr_distance", atr_multiplier=2.0),
        stop_offset_atr=0.5,
        target=TargetReference(kind="atr_distance", atr_multiplier=3.0),
        entry_trigger="at_price",
        valid_hours=24,
        leverage_intent="moderate",
        leverage_reasoning="standard conviction",
    )


def _final() -> FinalSignal:
    return FinalSignal(
        symbol="BTC/USDT:USDT",
        direction="long",
        setup_type="trend_continuation",
        entry_price=100.0,
        stop_price=98.0,
        target_price=103.0,
        risk_reward=1.5,
        valid_hours=24,
        confluence_score=0.6,
        analyst_confluence=0.6,
        invalidation="4h close below 98",
        thesis="momentum",
        key_risks=["funding"],
        leverage_intent="moderate",
    )


def test_fill_within_drift_reanchors_to_live_price():
    candles_4h = _candles(30, last_close=100.3)
    result = evaluate_fill(_intent(), _final(), 0.0, candles_4h, _candles(5))

    assert result.reason == REASON_SIGNAL_READY
    assert result.final_signal is not None
    assert result.final_signal.entry_price == 100.3
    assert result.final_signal.stop_price < 100.3 < result.final_signal.target_price
    assert result.final_signal.confluence_score == 0.6


def test_fill_beyond_drift_is_rejected():
    candles_4h = _candles(30, last_close=102.0)
    result = evaluate_fill(_intent(), _final(), 0.0, candles_4h, _candles(5))

    assert result.final_signal is None
    assert result.reason == REASON_ENTRY_DRIFT


def test_fill_no_candles_is_stale():
    result = evaluate_fill(_intent(), _final(), 0.0, [], [])

    assert result.final_signal is None
    assert result.reason == REASON_STALE_LEVELS
