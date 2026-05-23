from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from app.clients.lunarcrush_client import (
    CoinTimeSeriesPoint,
    LunarCrushCoinMetrics,
    LunarCrushNewsItem,
    LunarCrushPost,
    WhatsupSummary,
    WhatsupTheme,
)
from app.enricher.insight import derive_social_insight


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "selftest",
        help=(
            "Run mock-based smoke tests of the enrich business logic. "
            "No HTTP, no API quota — pure assertions on derive_social_insight."
        ),
    )
    p.set_defaults(handler=_handle)


def _handle(_args: argparse.Namespace) -> None:
    failures = 0
    for name, check in _CHECKS:
        try:
            check()
        except AssertionError as exc:
            print(f"FAIL  {name}: {exc}")
            failures += 1
        except Exception as exc:
            print(f"ERROR {name}: {type(exc).__name__}: {exc}")
            failures += 1
        else:
            print(f"PASS  {name}")

    total = len(_CHECKS)
    print(f"\n{total - failures}/{total} checks passed")
    if failures:
        sys.exit(1)


def _spike_bullish_long() -> None:
    """Hyped memecoin with bullish sentiment, screener says long → confirms + spike."""
    now = datetime.now(timezone.utc)
    lc = LunarCrushCoinMetrics(
        symbol="PEPE",
        topic="pepe",
        galaxy_score=68.5,
        galaxy_score_previous=62.0,
        alt_rank=42,
        alt_rank_previous=58,
        sentiment=78.0,
        social_volume_24h=15000,
        categories=["memecoin"],
    )
    ts = [
        CoinTimeSeriesPoint(time=now - timedelta(days=i), posts_active=4500 - i * 200)
        for i in range(7, 0, -1)
    ] + [CoinTimeSeriesPoint(time=now, posts_active=15000)]
    ins = derive_social_insight(
        lc=lc,
        news=[],
        posts=[],
        whatsup=None,
        time_series=ts,
        screener_direction="long",
        now=now,
    )
    assert ins.attention_level == "spike", ins.attention_level
    assert ins.sentiment_direction == "bullish", ins.sentiment_direction
    assert ins.screener_alignment == "confirms", ins.screener_alignment
    assert ins.momentum == "improving", ins.momentum
    assert ins.contrarian_warning is False
    assert ins.is_partial is False


def _contrarian_overheat() -> None:
    """Sentiment >= 85% triggers contrarian_warning even when alignment confirms."""
    lc = LunarCrushCoinMetrics(symbol="SOL", sentiment=92.0)
    ins = derive_social_insight(
        lc=lc,
        news=[],
        posts=[],
        whatsup=None,
        time_series=[],
        screener_direction="long",
    )
    assert ins.contrarian_warning is True
    assert ins.sentiment_direction == "bullish"
    assert ins.screener_alignment == "confirms"


def _screener_contradicts() -> None:
    """Screener says short but social is bullish → contradicts."""
    lc = LunarCrushCoinMetrics(symbol="ETH", sentiment=75.0)
    ins = derive_social_insight(
        lc=lc,
        news=[],
        posts=[],
        whatsup=None,
        time_series=[],
        screener_direction="short",
    )
    assert ins.screener_alignment == "contradicts", ins.screener_alignment


def _no_data_degrades_safely() -> None:
    """Complete absence of all sources → silent/unknown/no_data, is_partial=True."""
    ins = derive_social_insight(
        lc=None,
        news=[],
        posts=[],
        whatsup=None,
        time_series=[],
        screener_direction="long",
    )
    assert ins.attention_level == "silent"
    assert ins.sentiment_direction == "unknown"
    assert ins.screener_alignment == "no_data"
    assert ins.momentum == "unknown"
    assert ins.is_partial is True
    assert ins.sources_used == []


def _partial_only_lc_no_per_symbol() -> None:
    """LC list arrived but topic-endpoints failed → not partial (lc is enough core)."""
    lc = LunarCrushCoinMetrics(symbol="BTC", sentiment=55.0, social_volume_24h=50000)
    ins = derive_social_insight(
        lc=lc,
        news=[],
        posts=[],
        whatsup=None,
        time_series=[],
        screener_direction="long",
    )
    assert ins.is_partial is False, "lc present should mean not partial"
    assert ins.sentiment_direction == "mixed"


def _momentum_improving_both_signals() -> None:
    """galaxy ↑ + alt_rank ↑ (lower number) → improving."""
    lc = LunarCrushCoinMetrics(
        symbol="X",
        galaxy_score=70,
        galaxy_score_previous=60,
        alt_rank=10,
        alt_rank_previous=20,
    )
    ins = derive_social_insight(
        lc=lc,
        news=[],
        posts=[],
        whatsup=None,
        time_series=[],
        screener_direction="long",
    )
    assert ins.momentum == "improving", ins.momentum
    assert ins.galaxy_score_delta == 10
    assert ins.alt_rank_delta == 10


def _momentum_deteriorating() -> None:
    """Both metrics worse → deteriorating."""
    lc = LunarCrushCoinMetrics(
        symbol="X",
        galaxy_score=50,
        galaxy_score_previous=60,
        alt_rank=30,
        alt_rank_previous=20,
    )
    ins = derive_social_insight(
        lc=lc,
        news=[],
        posts=[],
        whatsup=None,
        time_series=[],
        screener_direction="long",
    )
    assert ins.momentum == "deteriorating", ins.momentum


def _fresh_catalyst_picked_by_engagement() -> None:
    """Most-engaging news within 24h becomes fresh_catalyst regardless of order."""
    now = datetime.now(timezone.utc)
    news = [
        LunarCrushNewsItem(
            id="n1",
            post_title="boring",
            post_created=now - timedelta(hours=2),
            post_sentiment=3.0,
            interactions_24h=10,
        ),
        LunarCrushNewsItem(
            id="n2",
            post_title="MAJOR LISTING",
            post_created=now - timedelta(hours=8),
            post_sentiment=4.5,
            interactions_24h=50000,
        ),
        LunarCrushNewsItem(
            id="n3",
            post_title="stale",
            post_created=now - timedelta(days=3),
            post_sentiment=4.0,
            interactions_24h=100000,  # high engagement but old
        ),
    ]
    ins = derive_social_insight(
        lc=None,
        news=news,
        posts=[],
        whatsup=None,
        time_series=[],
        screener_direction="long",
        now=now,
    )
    assert ins.fresh_catalyst is not None
    assert ins.fresh_catalyst.id == "n2", (
        f"expected n2 (high engagement, fresh), got {ins.fresh_catalyst.id}"
    )
    assert ins.catalyst_polarity == "positive"
    assert ins.important_news_count_24h == 2  # n1 and n2 (n3 too old)


def _influencer_split() -> None:
    """Posts with creator_followers >= 100k counted as influencer."""
    posts = [
        LunarCrushPost(
            id="p1", post_type="tweet", creator_followers=500_000, interactions_24h=100
        ),
        LunarCrushPost(
            id="p2", post_type="tweet", creator_followers=200, interactions_24h=10
        ),
        LunarCrushPost(
            id="p3", post_type="tweet", creator_followers=150_000, interactions_24h=50
        ),
    ]
    ins = derive_social_insight(
        lc=None,
        news=[],
        posts=posts,
        whatsup=None,
        time_series=[],
        screener_direction="long",
    )
    assert ins.influencer_mentions == 2, ins.influencer_mentions


def _whatsup_passthrough() -> None:
    """WhatsupSummary fields propagate to SocialInsight without mutation."""
    w = WhatsupSummary(
        summary="hello",
        supportive=[WhatsupTheme(title="t1", description="d1", percent=50.0)],
        critical=[WhatsupTheme(title="t2", description="d2", percent=20.0)],
    )
    ins = derive_social_insight(
        lc=None, news=[], posts=[], whatsup=w, time_series=[], screener_direction="long"
    )
    assert ins.narrative_summary == "hello"
    assert len(ins.supportive_themes) == 1
    assert len(ins.critical_themes) == 1


_CHECKS: list[tuple[str, Callable[[], None]]] = [
    ("spike + bullish + long → confirms + improving", _spike_bullish_long),
    ("contrarian overheat (sentiment 92)", _contrarian_overheat),
    ("screener contradicts social", _screener_contradicts),
    ("no data → silent / partial", _no_data_degrades_safely),
    ("only lc, no per-symbol → not partial", _partial_only_lc_no_per_symbol),
    ("momentum: both improving", _momentum_improving_both_signals),
    ("momentum: both deteriorating", _momentum_deteriorating),
    (
        "fresh catalyst by engagement, ignores stale",
        _fresh_catalyst_picked_by_engagement,
    ),
    ("influencer split by followers ≥ 100k", _influencer_split),
    ("whatsup passthrough", _whatsup_passthrough),
]
