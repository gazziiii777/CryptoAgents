from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CryptoSetup(BaseModel):
    direction: Literal["Long", "Short"]
    setup_type: Literal[
        "Trend Continuation", "Reversal", "Breakout", "Range Fade", "Liquidity Grab"
    ]
    entry_zone_low: float
    entry_zone_high: float
    entry_reasoning: str
    stop_loss: float
    stop_reasoning: str
    target_1: float
    target_2: float
    risk_reward: float
    invalidation_condition: str
    valid_hours: int
    funding_impact: str
    liquidity_target: str
    confidence: int = Field(ge=0, le=100)
    confidence_reasoning: str


class FinalSignal(BaseModel):
    ticker: str
    timestamp: str
    rating: Literal["Strong Long", "Long", "No Trade", "Short", "Strong Short"]
    entry_zone: str
    stop_loss: float
    target_1: float
    target_2: float
    risk_reward: float
    setup_type: str
    valid_until: str
    thesis: str
    key_risks: list[str]
    invalidation: str
    confluence_score: float
    confidence: int
    warnings: list[str]
