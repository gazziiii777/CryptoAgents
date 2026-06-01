from __future__ import annotations

from enum import StrEnum


class SignalSource(StrEnum):
    SCREENER = "screener"
    MANUAL = "manual"


class Direction(StrEnum):
    LONG = "long"
    SHORT = "short"
    NO_TRADE = "no_trade"


class Decision(StrEnum):
    TAKEN = "taken"
    SKIPPED_DEDUP = "skipped_dedup"
    SKIPPED_SLOT = "skipped_slot"
    SKIPPED_DRAWDOWN = "skipped_drawdown"
    SKIPPED_FUNDING = "skipped_funding"
    NO_TRADE = "no_trade"


class PositionState(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class PositionSide(StrEnum):
    LONG = "long"
    SHORT = "short"


class ExitReason(StrEnum):
    STOP = "stop"
    BREAKEVEN = "breakeven"
    TRAILING_STOP = "trailing_stop"
    TARGET = "target"
    INVALIDATION = "invalidation"
    EXPIRED = "expired"
    MANUAL = "manual"
    EXTREME_FUNDING = "extreme_funding"
    DELISTED = "delisted"


class EventType(StrEnum):
    SIGNAL_GENERATED = "signal_generated"
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"
    STOP_UPDATED = "stop_updated"
    CIRCUIT_BREAKER_TRIGGERED = "circuit_breaker_triggered"
    LLM_CALL = "llm_call"
    MANUAL_ACTION = "manual_action"
    RESTART_RECOVERY = "restart_recovery"
