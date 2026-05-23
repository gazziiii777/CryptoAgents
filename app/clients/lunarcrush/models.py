from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

_FROZEN = ConfigDict(frozen=True, extra="ignore")


class LunarCrushCoinMetrics(BaseModel):
    """Метрики из LunarCrush /coins/list/v1 для одной монеты.

    topic — slug для /topic/{topic}/* запросов: последнее слово из поля "topic"
    (напр. "btc bitcoin" → "bitcoin", "sol solana" → "solana").
    sentiment — 0..100 (% позитивных постов взвешенных по interactions).
    """

    model_config = _FROZEN

    symbol: str
    name: str | None = None
    topic: str | None = None
    galaxy_score: float | None = None
    galaxy_score_previous: float | None = None
    alt_rank: int | None = None
    alt_rank_previous: int | None = None
    sentiment: float | None = None
    social_volume_24h: int | None = None
    interactions_24h: int | None = None
    social_dominance: float | None = None
    categories: list[str] = []


class WhatsupTheme(BaseModel):
    """Тема из AI-summary LunarCrush /topic/{topic}/whatsup/v1."""

    model_config = _FROZEN

    title: str
    description: str
    percent: float


class WhatsupSummary(BaseModel):
    """AI-сгенерированный narrative от LunarCrush.

    Покрывает что обсуждается, какие supportive/critical темы. Заменяет
    отдельный LLM-вызов для narrative-анализа.
    """

    model_config = _FROZEN

    summary: str
    supportive: list[WhatsupTheme] = []
    critical: list[WhatsupTheme] = []


class LunarCrushPost(BaseModel):
    """Социальный пост от LunarCrush /topic/{topic}/posts/v1.

    creator_followers — ключевое поле для отделения retail от influencers.
    post_sentiment — 1-5 (1=very negative, 3=neutral, 5=very positive).
    """

    model_config = _FROZEN

    id: str
    post_type: str
    post_title: str | None = None
    post_link: str | None = None
    post_created: datetime | None = None
    post_sentiment: float | None = None
    creator_name: str | None = None
    creator_display_name: str | None = None
    creator_followers: int = 0
    interactions_24h: int = 0


class LunarCrushNewsItem(BaseModel):
    """Новость от LunarCrush /topic/{topic}/news/v1.

    Уже отсортированы по социальной обсуждаемости (top news = top in social),
    что лучше CryptoPanic-сортировки по community votes.
    """

    model_config = _FROZEN

    id: str
    post_title: str
    post_description: str | None = None
    post_link: str | None = None
    post_created: datetime | None = None
    post_sentiment: float | None = None
    creator_name: str | None = None
    creator_followers: int = 0
    interactions_24h: int = 0


class CoinTimeSeriesPoint(BaseModel):
    """Точка time-series для расчёта baseline по социальной активности."""

    model_config = _FROZEN

    time: datetime
    close: float | None = None
    sentiment: float | None = None
    interactions: int | None = None
    posts_active: int | None = None
    galaxy_score: float | None = None
    alt_rank: int | None = None
