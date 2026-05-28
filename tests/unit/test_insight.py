from datetime import datetime, timedelta, timezone

from app.clients.lunarcrush.models import (
    CoinTimeSeriesPoint,
    LunarCrushCoinMetrics,
    LunarCrushNewsItem,
    LunarCrushPost,
    WhatsupSummary,
    WhatsupTheme,
)
from app.enricher.insight import derive_social_insight


def test_spike_bullish_long_confirms_and_improving():
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
    assert ins.attention_level == "spike"
    assert ins.sentiment_direction == "bullish"
    assert ins.screener_alignment == "confirms"
    assert ins.momentum == "improving"
    assert ins.contrarian_warning is False
    assert ins.is_partial is False


def test_contrarian_overheat_triggers_warning():
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


def test_screener_contradicts_social():
    lc = LunarCrushCoinMetrics(symbol="ETH", sentiment=75.0)
    ins = derive_social_insight(
        lc=lc,
        news=[],
        posts=[],
        whatsup=None,
        time_series=[],
        screener_direction="short",
    )
    assert ins.screener_alignment == "contradicts"


def test_no_data_degrades_safely():
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


def test_only_lc_no_per_symbol_not_partial():
    lc = LunarCrushCoinMetrics(symbol="BTC", sentiment=55.0, social_volume_24h=50000)
    ins = derive_social_insight(
        lc=lc,
        news=[],
        posts=[],
        whatsup=None,
        time_series=[],
        screener_direction="long",
    )
    assert ins.is_partial is False
    assert ins.sentiment_direction == "mixed"


def test_momentum_improving_both_signals():
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
    assert ins.momentum == "improving"
    assert ins.galaxy_score_delta == 10
    assert ins.alt_rank_delta == 10


def test_momentum_deteriorating_both_signals():
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
    assert ins.momentum == "deteriorating"


def test_fresh_catalyst_picked_by_engagement_ignores_stale():
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
            interactions_24h=100000,
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
    assert ins.fresh_catalyst.id == "n2"
    assert ins.catalyst_polarity == "positive"
    assert ins.important_news_count_24h == 2


def test_influencer_split_by_followers():
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
    assert ins.influencer_mentions == 2


def test_whatsup_passthrough():
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
