from typing import Literal

from pydantic import BaseModel, Field


class EntryReference(BaseModel):
    """Откуда брать якорь входа (без цены — её резолвит LevelComputer)."""

    kind: Literal[
        "market", "swing_low_4h", "swing_high_4h", "prev_day_high", "prev_day_low"
    ] = Field(
        description="Entry anchor; 'market' enters at the current price (momentum entry)."
    )
    lookback: int | None = Field(
        default=None, description="Bars for swing refs (e.g. 10/20/50)."
    )


class StopReference(BaseModel):
    """Откуда брать якорь стопа."""

    kind: Literal["swing_low_4h", "swing_high_4h", "atr_distance"] = Field(
        description="Stop anchor: a swing level, or a pure ATR distance from entry."
    )
    lookback: int | None = Field(default=None, description="Bars for swing refs.")
    atr_multiplier: float | None = Field(
        default=None, description="ATR multiple for atr_distance stops (e.g. 2.0-3.0)."
    )


class TargetReference(BaseModel):
    """Откуда брать якорь цели."""

    kind: Literal[
        "swing_high_4h", "swing_low_4h", "prev_day_high", "prev_day_low", "atr_distance"
    ] = Field(
        description="Which level to target; atr_distance = measured move from entry."
    )
    lookback: int | None = Field(default=None, description="Bars for swing refs.")
    atr_multiplier: float | None = Field(
        default=None, description="ATR multiple from entry for atr_distance targets."
    )


class SetupIntent(BaseModel):
    """Вывод SetupBuilder (LLM): ЛОГИКА сетапа — типы и reference'ы, БЕЗ конкретных цен.

    Цены резолвит детерминированный LevelComputer (Python). LLM числа не пишет.
    """

    reasoning: str = Field(
        description="Reason FIRST, then choose setup_type and references to match it."
    )
    direction: Literal["long", "short"] = Field(description="Trade direction.")
    setup_type: Literal["trend_continuation", "breakout", "reversal"] = Field(
        description="Setup archetype."
    )
    entry: EntryReference
    entry_offset_atr: float = Field(
        ge=-3.0, le=3.0, description="Entry offset in ATR from its anchor (signed)."
    )
    stop: StopReference
    stop_offset_atr: float = Field(
        ge=0.1, le=3.0, description="Stop offset in ATR beyond its anchor."
    )
    target: TargetReference
    entry_trigger: Literal["at_price", "after_displacement"] = Field(
        description="Limit at price, or wait for a displacement candle."
    )
    valid_hours: int = Field(
        ge=4, le=168, description="Setup validity window in hours."
    )
    leverage_intent: Literal["conservative", "moderate", "aggressive"] = Field(
        description=(
            "Desired aggression of position leverage — NOT a number. "
            "conservative = low conviction / choppy regime / wide invalidation; "
            "moderate = standard conviction; aggressive = high conviction with a "
            "tight, well-defined invalidation. The system maps this to an actual "
            "leverage multiple by setup_type, under a hard cap."
        )
    )
    leverage_reasoning: str = Field(
        description="One sentence: why this aggression level fits the setup and risk."
    )


class CryptoSetup(BaseModel):
    """Вывод LevelComputer (Python): реальные цены из SetupIntent. LLM их НЕ пишет."""

    direction: Literal["long", "short"]
    setup_type: str
    entry_price: float
    stop_price: float
    target_price: float
    risk_reward: float
    valid_hours: int
    funding_impact_pct: float
    invalidation: str
    leverage_intent: Literal["conservative", "moderate", "aggressive"] = "moderate"


class FinalSignal(BaseModel):
    """Готовый сигнал: CryptoSetup-цены + синтез (bias/confluence/риски) + символ."""

    symbol: str
    direction: Literal["long", "short"]
    setup_type: str
    entry_price: float
    stop_price: float
    target_price: float
    risk_reward: float
    valid_hours: int
    confluence_score: float
    analyst_confluence: float = 0.0
    invalidation: str
    thesis: str
    key_risks: list[str]
    leverage_intent: Literal["conservative", "moderate", "aggressive"] = "moderate"
