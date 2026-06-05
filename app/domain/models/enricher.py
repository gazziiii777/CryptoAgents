from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.adapters.clients.coingecko.models import MacroSnapshot
from app.adapters.clients.lunarcrush.models import (
    LunarCrushNewsItem,
    LunarCrushPost,
    WhatsupTheme,
)
from app.domain.models.screener import ScreenerResult

_FROZEN = ConfigDict(frozen=True, extra="ignore")

AttentionLevel = Literal["silent", "normal", "spike"]
SentimentDirection = Literal["bullish", "bearish", "mixed", "unknown"]
ScreenerAlignment = Literal["confirms", "contradicts", "neutral", "no_data"]
CatalystPolarity = Literal["positive", "negative", "neutral"]
MomentumDirection = Literal["improving", "deteriorating", "flat", "unknown"]
PumpRisk = Literal["none", "moderate", "high"]


class SocialInsight(BaseModel):
    """Готовые ответы про настроение, momentum и катализаторы по кандидату.

    Детерминированная свёртка LunarCrush метрик + AI-narrative + новостей +
    топ-постов в структурированный сигнал. Используется и как gate
    (contrarian overheat, противоречие скринеру), и как структурированный
    вход для downstream LLM-агентов.
    """

    model_config = _FROZEN

    attention_level: AttentionLevel
    attention_ratio: float | None
    attention_baseline: float | None
    social_volume_24h: int | None
    interactions_24h: int | None

    galaxy_score: float | None
    galaxy_score_delta: float | None
    alt_rank: int | None
    alt_rank_delta: int | None
    momentum: MomentumDirection

    sentiment_pct: float | None
    sentiment_direction: SentimentDirection
    contrarian_warning: bool

    screener_alignment: ScreenerAlignment

    fresh_catalyst: LunarCrushNewsItem | None
    catalyst_polarity: CatalystPolarity | None
    important_news_count_24h: int
    top_news: list[LunarCrushNewsItem]

    narrative_summary: str | None
    supportive_themes: list[WhatsupTheme]
    critical_themes: list[WhatsupTheme]

    influencer_mentions: int
    top_posts: list[LunarCrushPost]

    categories: list[str]

    pump_risk: PumpRisk = "none"

    sources_used: list[str]
    is_partial: bool


class EnrichedCandidate(BaseModel):
    """Кандидат скринера + готовые социальные/новостные ответы.

    Macro живёт отдельно на уровне pipeline (один MacroSnapshot на прогон),
    в EnrichedCandidate не дублируется — режет контекст downstream LLM и
    устраняет рассинхрон между кандидатами одного батча.

    lc_context — LLM-оптимизированный markdown от lunarcrush.ai: engagements/
    mentions по сетям, топ-инфлюенсеры, история sentiment/galaxy/altrank.
    Передаётся напрямую в LLM-аналитиков без дополнительной обработки.
    """

    symbol: str
    screener: ScreenerResult
    social: SocialInsight
    lc_context: str | None = None
    enriched_at: datetime


class EnrichmentResult(BaseModel):
    """Полный результат прогона энричера: per-symbol-кандидаты + общий macro."""

    candidates: list[EnrichedCandidate]
    macro: MacroSnapshot
    fear_greed: int | None = None
