from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.enricher import EnrichedCandidate
from app.models.setup import CryptoSetup, FinalSignal, SetupIntent


class MacroReport(BaseModel):
    reasoning: str = Field(
        description="Brief rationale (1-3 sentences) citing the specific figures. "
        "Reason here FIRST, then set the classification fields to match it."
    )
    regime: Literal["Trending Up", "Trending Down", "Ranging", "High Volatility"] = (
        Field(description="Market regime from BTC 24h/7d action and market-cap moves.")
    )
    btc_bias: Literal["Bullish", "Bearish", "Neutral"] = Field(
        description="Directional lean for BTC over the next few 4h candles."
    )
    dominance_trend: Literal["Rising", "Falling", "Flat"] = Field(
        description="Direction of BTC dominance."
    )
    alts_tradeable: bool = Field(
        description="True only if conditions favor opening altcoin positions now."
    )


class DerivativesReport(BaseModel):
    key_insight: str = Field(
        description="Reason through the derivatives data FIRST (1-3 sentences), then "
        "set the fields to follow from it."
    )
    funding_signal: Literal[
        "Extreme Long", "Elevated Long", "Neutral", "Elevated Short", "Extreme Short"
    ] = Field(description="Funding-rate positioning; positive/high = crowded longs.")
    oi_signal: Literal["Confirming", "Diverging", "Neutral"] = Field(
        description="Open interest vs price: confirming the move or diverging."
    )
    ls_signal: Literal["Longs Crowded", "Shorts Crowded", "Balanced"] = Field(
        description="Long/short ratio crowding (retail vs top traders)."
    )
    liq_nearest_long: float | None = Field(
        description="Nearest long-liquidation price, or null if not provided."
    )
    liq_nearest_short: float | None = Field(
        description="Nearest short-liquidation price, or null if not provided."
    )
    cvd_direction: Literal["Accumulation", "Distribution", "Neutral"] = Field(
        description="Cumulative volume delta: net buying (accumulation) or selling."
    )
    overall_bias: Literal["Bullish", "Bearish", "Neutral"] = Field(
        description="Net directional bias from the derivatives picture."
    )


class SentimentReport(BaseModel):
    key_insight: str = Field(
        description="Reason through the social/news data FIRST (1-3 sentences), then "
        "set the fields to follow from it."
    )
    social_sentiment: Literal[
        "Very Bullish", "Bullish", "Neutral", "Bearish", "Very Bearish"
    ] = Field(
        description="Overall social sentiment from sentiment %, attention, momentum."
    )
    fear_greed_label: Literal[
        "Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed"
    ] = Field(description="Fear & Greed index bucket (0-100 → label).")
    news_sentiment: Literal["Positive", "Neutral", "Negative"] = Field(
        description="Tone of recent news / catalysts."
    )
    overall_bias: Literal["Bullish", "Bearish", "Neutral"] = Field(
        description="Net directional bias from sentiment."
    )


class KeyLevel(BaseModel):
    price: float = Field(
        description="Price of the level; use ONLY values present in the provided data."
    )
    type: Literal["support", "resistance"] = Field(
        description="Support (below price) or resistance (above price)."
    )
    strength: Literal["strong", "moderate", "weak"] = Field(
        description="How significant the level is."
    )


class TechnicalReport(BaseModel):
    market_structure: str = Field(
        description="Read the structure FIRST (1-3 sentences): trend, recent swings, "
        "where price sits vs the key levels. Then fill the rest to follow from it."
    )
    htf_bias: Literal["Bullish", "Bearish", "Neutral"] = Field(
        description="Higher-timeframe (1d) directional bias."
    )
    setup_bias: Literal["Bullish", "Bearish", "Neutral"] = Field(
        description="4h setup directional bias."
    )
    key_levels: list[KeyLevel] = Field(
        description="Most relevant support/resistance, chosen ONLY from provided levels."
    )
    entry_timeframe_note: str = Field(description="Short note on the 4h entry context.")
    signal_direction: Literal["Long", "Short", "No Signal"] = Field(
        description="Tradeable direction, or No Signal if structure is unclear."
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence 0-1 in the signal direction."
    )


class SignalSynthesis(BaseModel):
    overall_bias: Literal["Bullish", "Bearish", "Neutral"]
    confluence_score: float = Field(ge=0.0, le=1.0)
    has_significant_conflict: bool
    scores_by_analyst: dict[str, float]
    top_risks: list[str]
    reasoning: str


class ResearchCase(BaseModel):
    """Аргумент Bull- или Bear-исследователя: тезис, пункты, сила убеждённости."""

    thesis: str = Field(
        description="The strongest case for this side in 2-4 sentences."
    )
    key_points: list[str] = Field(
        description="Concrete evidence bullets drawn ONLY from the provided reports."
    )
    conviction: float = Field(
        ge=0.0, le=1.0, description="Strength of THIS side's case, 0-1."
    )


class TraderVerdict(BaseModel):
    """Решение трейдера после взвешивания bull vs bear кейсов."""

    verdict: Literal["long", "short", "no_trade"] = Field(
        description="Final call after weighing the bull and bear cases."
    )
    conviction: float = Field(
        ge=0.0, le=1.0, description="Confidence in the verdict, 0-1."
    )
    reasoning: str = Field(
        description="Which case is stronger and why; what would invalidate the call."
    )


class DevilsAdvocateReport(BaseModel):
    """Финальная попытка опровергнуть готовый сетап перед открытием позиции."""

    assessment: str = Field(
        description="Honest red-team review of the proposed trade in 2-4 sentences."
    )
    critical_risks: list[str] = Field(
        description="ONLY material, trade-invalidating risks (crowded trade, liquidity "
        "trap, macro/regulatory headwind, structure that contradicts the entry). "
        "Empty list if the setup is genuinely clean — do not pad it."
    )


class CandidateSignal(BaseModel):
    """Полный аналитический результат по кандидату: входы + 4 отчёта + синтез.

    Снапшот для персиста (Event signal_generated) — для анализа слабых мест.
    """

    candidate: EnrichedCandidate
    macro: MacroReport
    derivatives: DerivativesReport
    sentiment: SentimentReport
    technical: TechnicalReport
    synthesis: SignalSynthesis
    bar_close_ts: datetime
    bull_case: ResearchCase | None = None
    bear_case: ResearchCase | None = None
    trader_verdict: TraderVerdict | None = None
    devils_advocate: DevilsAdvocateReport | None = None
    setup_intent: SetupIntent | None = None
    crypto_setup: CryptoSetup | None = None
    final_signal: FinalSignal | None = None
    decision_reason: str = "pending"
