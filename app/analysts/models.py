from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class MacroReport(BaseModel):
    regime: Literal["Trending Up", "Trending Down", "Ranging", "High Volatility"]
    btc_bias: Literal["Bullish", "Bearish", "Neutral"]
    dominance_trend: Literal["Rising", "Falling", "Flat"]
    alts_tradeable: bool
    reasoning: str


class DerivativesReport(BaseModel):
    funding_signal: Literal[
        "Extreme Long", "Elevated Long", "Neutral", "Elevated Short", "Extreme Short"
    ]
    oi_signal: Literal["Confirming", "Diverging", "Neutral"]
    ls_signal: Literal["Longs Crowded", "Shorts Crowded", "Balanced"]
    liq_nearest_long: float | None
    liq_nearest_short: float | None
    cvd_direction: Literal["Accumulation", "Distribution", "Neutral"]
    overall_bias: Literal["Bullish", "Bearish", "Neutral"]
    key_insight: str


class SentimentReport(BaseModel):
    social_sentiment: Literal[
        "Very Bullish", "Bullish", "Neutral", "Bearish", "Very Bearish"
    ]
    fear_greed_label: Literal[
        "Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed"
    ]
    news_sentiment: Literal["Positive", "Neutral", "Negative"]
    overall_bias: Literal["Bullish", "Bearish", "Neutral"]
    key_insight: str


class KeyLevel(BaseModel):
    price: float
    type: Literal["support", "resistance"]
    strength: Literal["strong", "moderate", "weak"]


class TechnicalReport(BaseModel):
    htf_bias: Literal["Bullish", "Bearish", "Neutral"]
    setup_bias: Literal["Bullish", "Bearish", "Neutral"]
    key_levels: list[KeyLevel]
    market_structure: str
    entry_timeframe_note: str
    signal_direction: Literal["Long", "Short", "No Signal"]
    confidence: float = Field(ge=0.0, le=1.0)


class SignalSynthesis(BaseModel):
    overall_bias: Literal["Bullish", "Bearish", "Neutral"]
    confluence_score: float = Field(ge=0.0, le=1.0)
    has_significant_conflict: bool
    scores_by_analyst: dict[str, float]
    top_risks: list[str]
    reasoning: str
