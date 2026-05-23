from __future__ import annotations

from datetime import datetime, timezone

from app.clients.lunarcrush.models import (
    CoinTimeSeriesPoint,
    LunarCrushNewsItem,
    LunarCrushPost,
)


def parse_categories(raw: object) -> list[str]:
    if not raw or not isinstance(raw, str):
        return []
    return [c.strip() for c in raw.split(",") if c.strip()]


def safe_float(v: object) -> float | None:
    if v is None:
        return None
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def safe_int(v: object) -> int | None:
    if v is None:
        return None
    try:
        return int(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def safe_datetime(ts: object) -> datetime | None:
    """Unix timestamp (seconds) → tz-aware UTC datetime."""
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc)  # type: ignore[arg-type]
    except (TypeError, ValueError, OSError):
        return None


def optional_str(v: object) -> str | None:
    if v is None:
        return None
    s = str(v)
    return s if s else None


def parse_news_item(item: dict[str, object]) -> LunarCrushNewsItem:
    return LunarCrushNewsItem(
        id=str(item.get("id") or ""),
        post_title=str(item.get("post_title") or ""),
        post_description=optional_str(item.get("post_description")),
        post_link=optional_str(item.get("post_link")),
        post_created=safe_datetime(item.get("post_created")),
        post_sentiment=safe_float(item.get("post_sentiment")),
        creator_name=optional_str(item.get("creator_name")),
        creator_followers=safe_int(item.get("creator_followers")) or 0,
        interactions_24h=safe_int(item.get("interactions_24h")) or 0,
    )


def parse_post(item: dict[str, object]) -> LunarCrushPost:
    return LunarCrushPost(
        id=str(item.get("id") or ""),
        post_type=str(item.get("post_type") or ""),
        post_title=optional_str(item.get("post_title")),
        post_link=optional_str(item.get("post_link")),
        post_created=safe_datetime(item.get("post_created")),
        post_sentiment=safe_float(item.get("post_sentiment")),
        creator_name=optional_str(item.get("creator_name")),
        creator_display_name=optional_str(item.get("creator_display_name")),
        creator_followers=safe_int(item.get("creator_followers")) or 0,
        interactions_24h=safe_int(item.get("interactions_24h")) or 0,
    )


def parse_ts_point(item: dict[str, object]) -> CoinTimeSeriesPoint:
    return CoinTimeSeriesPoint(
        time=safe_datetime(item.get("time")) or datetime.now(timezone.utc),
        close=safe_float(item.get("close")),
        sentiment=safe_float(item.get("sentiment")),
        interactions=safe_int(item.get("interactions")),
        posts_active=safe_int(item.get("posts_active")),
        galaxy_score=safe_float(item.get("galaxy_score")),
        alt_rank=safe_int(item.get("alt_rank")),
    )
