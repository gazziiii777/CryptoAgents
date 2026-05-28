from app.agents.setup.graph import build_setup
from app.agents.setup.nodes import _validate_intent
from app.models.analysis import TechnicalReport
from app.models.setup import EntryReference, SetupIntent, StopReference, TargetReference

_TECH = TechnicalReport(
    market_structure="uptrend, price above EMAs",
    htf_bias="Bullish",
    setup_bias="Bullish",
    key_levels=[],
    entry_timeframe_note="pullback",
    signal_direction="Long",
    confidence=0.6,
)


def _intent(direction: str = "long", target_kind: str = "swing_high_4h") -> SetupIntent:
    return SetupIntent(
        reasoning="r",
        direction=direction,  # type: ignore[arg-type]
        setup_type="trend_continuation",
        entry=EntryReference(kind="swing_low_4h", lookback=20),
        entry_offset_atr=0.0,
        stop=StopReference(kind="atr_distance", atr_multiplier=2.0),
        stop_offset_atr=0.5,
        target=TargetReference(kind=target_kind),  # type: ignore[arg-type]
        entry_trigger="at_price",
        valid_hours=8,
        leverage_intent="moderate",
        leverage_reasoning="standard conviction",
    )


class _FakeService:
    def __init__(self, intents: list[SetupIntent]) -> None:
        self._intents = intents
        self.calls = 0

    async def structured(self, **kwargs: object) -> SetupIntent:
        intent = self._intents[self.calls]
        self.calls += 1
        return intent


def test_validate_intent_long_rules():
    assert _validate_intent(_intent(), "long") is None
    assert _validate_intent(_intent(target_kind="swing_low_4h"), "long") is not None
    assert _validate_intent(_intent(direction="short"), "long") is not None


async def test_build_setup_valid_on_first_try():
    service = _FakeService([_intent()])
    result = await build_setup(service, "long", _TECH, 100.0, 1.0)  # type: ignore[arg-type]
    assert result is not None
    assert service.calls == 1


async def test_build_setup_retries_then_succeeds():
    service = _FakeService([_intent(target_kind="swing_low_4h"), _intent()])
    result = await build_setup(service, "long", _TECH, 100.0, 1.0)  # type: ignore[arg-type]
    assert result is not None
    assert result.target.kind == "swing_high_4h"
    assert service.calls == 2


async def test_build_setup_gives_up_after_retry():
    invalid = _intent(target_kind="swing_low_4h")
    service = _FakeService([invalid, invalid])
    result = await build_setup(service, "long", _TECH, 100.0, 1.0)  # type: ignore[arg-type]
    assert result is None
    assert service.calls == 2
