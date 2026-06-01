import logging
from string import Template
from typing import Literal

from app.agents.setup.state import SetupState
from app.llm_gateway.service import LLMService
from app.models.setup import SetupIntent
from core.constants.setup_kinds import (
    KIND_ATR_DISTANCE,
    KIND_PREV_DAY_HIGH,
    KIND_PREV_DAY_LOW,
    KIND_SWING_HIGH_4H,
    KIND_SWING_LOW_4H,
)
from core.prompts.loader import load_prompt
from core.settings import settings

logger = logging.getLogger(__name__)

_ENTITY_TYPE = "setup"
_MAX_ATTEMPTS = 2

_LONG_STOP_KINDS = frozenset({KIND_SWING_LOW_4H, KIND_ATR_DISTANCE})
_LONG_TARGET_KINDS = frozenset({
    KIND_SWING_HIGH_4H,
    KIND_PREV_DAY_HIGH,
    KIND_ATR_DISTANCE,
})
_SHORT_STOP_KINDS = frozenset({KIND_SWING_HIGH_4H, KIND_ATR_DISTANCE})
_SHORT_TARGET_KINDS = frozenset({
    KIND_SWING_LOW_4H,
    KIND_PREV_DAY_LOW,
    KIND_ATR_DISTANCE,
})


def _validate_intent(
    intent: SetupIntent, direction: Literal["long", "short"]
) -> str | None:
    """Проверка направленной согласованности reference'ов. None = валидно."""
    if intent.direction != direction:
        return f"direction must be '{direction}', got '{intent.direction}'"
    stop_kinds = _LONG_STOP_KINDS if direction == "long" else _SHORT_STOP_KINDS
    target_kinds = _LONG_TARGET_KINDS if direction == "long" else _SHORT_TARGET_KINDS
    if intent.stop.kind not in stop_kinds:
        return (
            f"for {direction}, stop.kind must be one of {sorted(stop_kinds)}, "
            f"got '{intent.stop.kind}'"
        )
    if intent.target.kind not in target_kinds:
        return (
            f"for {direction}, target.kind must be one of {sorted(target_kinds)}, "
            f"got '{intent.target.kind}'"
        )
    return None


def _render_user_prompt(template: str, state: SetupState) -> str:
    technical = state.technical
    levels = (
        "; ".join(
            f"{level.type} {level.price:.6g} ({level.strength})"
            for level in technical.key_levels
        )
        or "none"
    )
    atr_pct = state.atr / state.current_price * 100 if state.current_price else 0.0
    return Template(template).substitute(
        direction=state.direction,
        current_price=f"{state.current_price:.6g}",
        atr=f"{state.atr:.6g}",
        atr_pct=f"{atr_pct:.2f}",
        market_structure=technical.market_structure,
        htf_bias=technical.htf_bias,
        setup_bias=technical.setup_bias,
        signal_direction=technical.signal_direction,
        key_levels=levels,
        correction=state.validation_error or "(none)",
    )


async def build_node(
    state: SetupState, *, service: LLMService
) -> dict[str, SetupIntent | int]:
    """Нода 1: LLM строит SetupIntent (deep-модель)."""
    prompt = load_prompt(_ENTITY_TYPE)
    intent = await service.structured(
        model=settings.LLM_DEEP_MODEL,
        system=prompt.system,
        user=_render_user_prompt(prompt.user, state),
        response_model=SetupIntent,
        entity_type=_ENTITY_TYPE,
    )
    return {"intent": intent, "attempts": state.attempts + 1}


def validate_node(state: SetupState) -> dict[str, str | None]:
    """Нода 2: проверка constraints → validation_error (None если ок)."""
    if state.intent is None:
        return {"validation_error": "no intent produced"}
    error = _validate_intent(state.intent, state.direction)
    if error is not None:
        logger.info("setup intent invalid (attempt %d): %s", state.attempts, error)
    return {"validation_error": error}


def route_after_validate(state: SetupState) -> str:
    """Conditional edge: retry (один re-prompt) при ошибке, иначе end."""
    if state.validation_error is not None and state.attempts < _MAX_ATTEMPTS:
        return "retry"
    return "end"
