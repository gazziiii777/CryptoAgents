from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.clients.lunarcrush.models import (
    CoinTimeSeriesPoint,
    LunarCrushCoinMetrics,
    LunarCrushNewsItem,
    LunarCrushPost,
    WhatsupSummary,
    WhatsupTheme,
)
from core import settings

_FROZEN = ConfigDict(frozen=True, extra="ignore")

AttentionLevel = Literal["silent", "normal", "spike"]
SentimentDirection = Literal["bullish", "bearish", "mixed", "unknown"]
ScreenerAlignment = Literal["confirms", "contradicts", "neutral", "no_data"]
CatalystPolarity = Literal["positive", "negative", "neutral"]
MomentumDirection = Literal["improving", "deteriorating", "flat", "unknown"]


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

    sources_used: list[str]
    is_partial: bool


def derive_social_insight(
    *,
    lc: LunarCrushCoinMetrics | None,
    news: list[LunarCrushNewsItem],
    posts: list[LunarCrushPost],
    whatsup: WhatsupSummary | None,
    time_series: list[CoinTimeSeriesPoint],
    screener_direction: str,
    now: datetime | None = None,
) -> SocialInsight:
    """Свернуть все LunarCrush-данные + scrap данные в SocialInsight."""
    now_utc = now or datetime.now(timezone.utc)

    sources: list[str] = []
    if lc is not None:
        sources.append("lunarcrush:list")
    if whatsup is not None:
        sources.append("lunarcrush:whatsup")
    if news:
        sources.append("lunarcrush:news")
    if posts:
        sources.append("lunarcrush:posts")
    if time_series:
        sources.append("lunarcrush:timeseries")

    baseline = _attention_baseline(time_series)
    social_volume_24h = lc.social_volume_24h if lc else None
    attention_ratio = _attention_ratio(social_volume_24h, baseline)
    attention_level = _attention_level(attention_ratio)

    sentiment_pct = lc.sentiment if lc else None
    sentiment_direction = _sentiment_direction(sentiment_pct)
    contrarian_warning = _contrarian_warning(sentiment_pct)
    screener_alignment = _screener_alignment(sentiment_pct, screener_direction)

    galaxy_delta = _delta_float(
        lc.galaxy_score if lc else None, lc.galaxy_score_previous if lc else None
    )
    alt_rank_delta = _delta_alt_rank(
        lc.alt_rank if lc else None, lc.alt_rank_previous if lc else None
    )
    momentum = _momentum(galaxy_delta, alt_rank_delta)

    fresh_window = timedelta(hours=settings.NEWS_FRESH_CATALYST_WINDOW_H)
    fresh_news = [
        n
        for n in news
        if n.post_created is not None
        and (now_utc - _aware(n.post_created)) <= fresh_window
    ]
    fresh_catalyst = max(fresh_news, key=lambda n: n.interactions_24h, default=None)
    catalyst_polarity = (
        _news_polarity(fresh_catalyst.post_sentiment) if fresh_catalyst else None
    )

    top_news = sorted(news, key=lambda n: n.interactions_24h, reverse=True)[
        : settings.NEWS_TOP_K
    ]

    influencer_threshold = settings.LUNARCRUSH_INFLUENCER_FOLLOWERS_THRESHOLD
    influencer_mentions = sum(
        1 for p in posts if p.creator_followers >= influencer_threshold
    )
    top_posts = sorted(posts, key=lambda p: p.interactions_24h, reverse=True)[
        : settings.NEWS_TOP_K
    ]

    return SocialInsight(
        attention_level=attention_level,
        attention_ratio=attention_ratio,
        attention_baseline=baseline,
        social_volume_24h=social_volume_24h,
        interactions_24h=lc.interactions_24h if lc else None,
        galaxy_score=lc.galaxy_score if lc else None,
        galaxy_score_delta=galaxy_delta,
        alt_rank=lc.alt_rank if lc else None,
        alt_rank_delta=alt_rank_delta,
        momentum=momentum,
        sentiment_pct=sentiment_pct,
        sentiment_direction=sentiment_direction,
        contrarian_warning=contrarian_warning,
        screener_alignment=screener_alignment,
        fresh_catalyst=fresh_catalyst,
        catalyst_polarity=catalyst_polarity,
        important_news_count_24h=len(fresh_news),
        top_news=top_news,
        narrative_summary=whatsup.summary if whatsup else None,
        supportive_themes=whatsup.supportive if whatsup else [],
        critical_themes=whatsup.critical if whatsup else [],
        influencer_mentions=influencer_mentions,
        top_posts=top_posts,
        categories=lc.categories if lc else [],
        sources_used=sources,
        is_partial=lc is None,
    )


def _attention_baseline(time_series: list[CoinTimeSeriesPoint]) -> float | None:
    """Среднее posts_active за baseline-окно.

    Последняя точка time-series исключается: при bucket=day она представляет
    текущий неполный день, у которого posts_active ещё не накопился до
    реального значения — включение исказило бы baseline вниз. Сравнение
    идёт между live social_volume_24h (из /coins/list/v1) и средним по
    предыдущим полным дням.
    """
    if not time_series:
        return None
    days = settings.LUNARCRUSH_BASELINE_DAYS
    history = [p.posts_active for p in time_series[:-1] if p.posts_active is not None]
    history = history[-days:]
    if not history:
        return None
    return sum(history) / len(history)


def _attention_ratio(
    social_volume_24h: int | None, baseline: float | None
) -> float | None:
    if social_volume_24h is None or baseline is None or baseline <= 0:
        return None
    return social_volume_24h / baseline


def _attention_level(ratio: float | None) -> AttentionLevel:
    if ratio is None:
        return "silent"
    if ratio >= settings.LUNARCRUSH_ATTENTION_RATIO_SPIKE:
        return "spike"
    if ratio >= settings.LUNARCRUSH_ATTENTION_RATIO_NORMAL:
        return "normal"
    return "silent"


def _sentiment_direction(sentiment_pct: float | None) -> SentimentDirection:
    if sentiment_pct is None:
        return "unknown"
    if sentiment_pct >= settings.LUNARCRUSH_SENTIMENT_BULLISH_THRESHOLD:
        return "bullish"
    if sentiment_pct <= settings.LUNARCRUSH_SENTIMENT_BEARISH_THRESHOLD:
        return "bearish"
    return "mixed"


def _contrarian_warning(sentiment_pct: float | None) -> bool:
    if sentiment_pct is None:
        return False
    return (
        sentiment_pct >= settings.LUNARCRUSH_CONTRARIAN_HIGH
        or sentiment_pct <= settings.LUNARCRUSH_CONTRARIAN_LOW
    )


def _screener_alignment(
    sentiment_pct: float | None, screener_direction: str
) -> ScreenerAlignment:
    if sentiment_pct is None or screener_direction == "mixed":
        return "no_data" if sentiment_pct is None else "neutral"
    bullish_t = settings.LUNARCRUSH_SENTIMENT_BULLISH_THRESHOLD
    bearish_t = settings.LUNARCRUSH_SENTIMENT_BEARISH_THRESHOLD
    if screener_direction == "long":
        if sentiment_pct >= bullish_t:
            return "confirms"
        if sentiment_pct <= bearish_t:
            return "contradicts"
        return "neutral"
    if screener_direction == "short":
        if sentiment_pct <= bearish_t:
            return "confirms"
        if sentiment_pct >= bullish_t:
            return "contradicts"
        return "neutral"
    return "no_data"


def _delta_float(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None:
        return None
    return current - previous


def _delta_alt_rank(current: int | None, previous: int | None) -> int | None:
    """alt_rank меньше = лучше. Возвращает (prev - curr): положительное = поднялся в рейтинге."""
    if current is None or previous is None:
        return None
    return previous - current


def _momentum(
    galaxy_delta: float | None, alt_rank_delta: int | None
) -> MomentumDirection:
    """Composite momentum по двум сигналам (galaxy и alt_rank).

    Обе метрики «улучшаются» — improving; обе «ухудшаются» — deteriorating;
    смешанные или нулевые — flat; нет данных — unknown.
    """
    if galaxy_delta is None and alt_rank_delta is None:
        return "unknown"
    galaxy_pos = (galaxy_delta or 0) > 0
    galaxy_neg = (galaxy_delta or 0) < 0
    rank_pos = (alt_rank_delta or 0) > 0
    rank_neg = (alt_rank_delta or 0) < 0
    if galaxy_pos and rank_pos:
        return "improving"
    if galaxy_neg and rank_neg:
        return "deteriorating"
    if (galaxy_pos or rank_pos) and not (galaxy_neg or rank_neg):
        return "improving"
    if (galaxy_neg or rank_neg) and not (galaxy_pos or rank_pos):
        return "deteriorating"
    return "flat"


def _news_polarity(post_sentiment: float | None) -> CatalystPolarity | None:
    """LunarCrush post_sentiment: 1-5, где 3=neutral."""
    if post_sentiment is None:
        return None
    if post_sentiment >= settings.LUNARCRUSH_POST_SENTIMENT_BULLISH:
        return "positive"
    if post_sentiment <= settings.LUNARCRUSH_POST_SENTIMENT_BEARISH:
        return "negative"
    return "neutral"


def _aware(dt: datetime) -> datetime:
    """Гарантирует tz-aware datetime в UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
