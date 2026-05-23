from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

from app.clients.lunarcrush_client import (
    CoinTimeSeriesPoint,
    LunarCrushCoinMetrics,
    LunarCrushNewsItem,
    LunarCrushPost,
    WhatsupSummary,
    WhatsupTheme,
)
from app.enricher.enricher import DataEnricher, EnrichedCandidate, EnrichmentResult
from app.enricher.insight import derive_social_insight
from app.screener.criteria import ScreenerResult, empty_signals
from app.screener.screener import run_screener


_DEFAULT_SYMBOLS = [
    "BTC/USDT:USDT",
    "ETH/USDT:USDT",
    "SOL/USDT:USDT",
    "BNB/USDT:USDT",
    "SUI/USDT:USDT",
]


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "enrich",
        help=(
            "Run the full enrich pipeline (screener → LunarCrush + macro). "
            "Use --mock to skip HTTP, --symbols to skip screener and use fixed coins."
        ),
    )
    p.add_argument(
        "--mock",
        action="store_true",
        help=(
            "Skip all HTTP calls; build EnrichmentResult from in-memory mock data. "
            "Useful for testing module wiring without spending API quota."
        ),
    )
    p.add_argument(
        "--symbols",
        nargs="*",
        metavar="SYMBOL",
        help=(
            "Skip screener, enrich these symbols directly with real API calls. "
            "Accepts base names (BTC, ETH) or full CCXT pairs (BTC/USDT:USDT). "
            "If flag given with no args, uses a default set of 5 major coins."
        ),
    )
    p.set_defaults(handler=_handle)


async def _handle(args: argparse.Namespace) -> None:
    if args.mock:
        _print_result(_build_mock_result())
        return

    if args.symbols is not None:
        symbols = args.symbols if args.symbols else _DEFAULT_SYMBOLS
        candidates = _build_stub_candidates(symbols)
    else:
        candidates = await run_screener()

    if not candidates:
        print("No candidates — nothing to enrich.")
        return

    enricher = DataEnricher()
    result = await enricher.enrich(candidates)
    _print_result(result)


def _build_stub_candidates(symbols: list[str]) -> list[ScreenerResult]:
    """Создаёт заглушки ScreenerResult для произвольных символов.

    Позволяет тестировать enricher без запуска скринера. Все технические
    сигналы нейтральны — важен только symbol для LunarCrush/CoinGecko запросов.
    """
    results = []
    for sym in symbols:
        full = sym if "/" in sym else f"{sym}/USDT:USDT"
        results.append(
            ScreenerResult(
                symbol=full,
                gate_passed=True,
                score=0,
                adx=0.0,
                direction="mixed",
                signals=empty_signals(),
            )
        )
    return results


def _print_result(result: EnrichmentResult) -> None:
    m = result.macro
    print("=" * 70)
    print("MACRO")
    print("=" * 70)
    print(
        f"  BTC: ${m.btc_price_usd:,.0f}  24h={m.btc_change_24h:+.2f}%  "
        f"7d={m.btc_change_7d:+.2f}%  dom={m.btc_dominance:.1f}%  "
        f"total_mc_24h={m.total_market_cap_change_24h:+.2f}%"
    )
    if result.fear_greed is not None:
        print(f"  Fear & Greed: {result.fear_greed}")

    print()
    print("=" * 70)
    print(f"CANDIDATES ({len(result.candidates)})")
    print("=" * 70)
    for c in result.candidates:
        _print_candidate(c)


def _print_candidate(c: EnrichedCandidate) -> None:
    s = c.social
    print(
        f"\n  {c.symbol}  screener_score={c.screener.score} direction={c.screener.direction}"
    )
    print(
        f"    attention: {s.attention_level} (ratio="
        f"{f'{s.attention_ratio:.2f}' if s.attention_ratio is not None else 'n/a'} "
        f"baseline={f'{s.attention_baseline:.0f}' if s.attention_baseline is not None else 'n/a'})"
    )
    print(
        f"    sentiment: {s.sentiment_direction} ("
        f"{f'{s.sentiment_pct:.0f}%' if s.sentiment_pct is not None else 'n/a'})  "
        f"contrarian={s.contrarian_warning}  alignment={s.screener_alignment}"
    )
    print(
        f"    momentum: {s.momentum}  galaxy="
        f"{f'{s.galaxy_score:.1f}' if s.galaxy_score is not None else 'n/a'}"
        f"({_signed(s.galaxy_score_delta)})  alt_rank={s.alt_rank}({_signed(s.alt_rank_delta)})"
    )
    if s.fresh_catalyst:
        print(
            f"    catalyst[{s.catalyst_polarity}]: {s.fresh_catalyst.post_title[:80]}"
        )
    if s.narrative_summary:
        print(f"    narrative: {s.narrative_summary[:120]}")
    if s.influencer_mentions:
        print(f"    influencers: {s.influencer_mentions} posts")
    if s.categories:
        print(f"    categories: {', '.join(s.categories[:3])}")
    if c.lc_context:
        print(f"    ai_context: {c.lc_context[:200].strip()!r}")
    print(f"    sources: {', '.join(s.sources_used) or 'none'}  partial={s.is_partial}")


def _signed(v: float | int | None) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v:+.1f}"
    return f"{v:+d}"


def _build_mock_result() -> EnrichmentResult:
    now = datetime.now(timezone.utc)

    from app.clients.coingecko_client import MacroSnapshot

    macro = MacroSnapshot(
        btc_dominance=53.2,
        btc_price_usd=68420.0,
        btc_change_24h=1.2,
        btc_change_7d=-3.4,
        total_market_cap_change_24h=0.8,
    )

    lc_pepe = LunarCrushCoinMetrics(
        symbol="PEPE",
        topic="pepe",
        name="Pepe",
        galaxy_score=68.5,
        galaxy_score_previous=62.0,
        alt_rank=42,
        alt_rank_previous=58,
        sentiment=78.0,
        social_volume_24h=15000,
        interactions_24h=320000,
        social_dominance=2.3,
        categories=["memecoin", "solana-ecosystem"],
    )
    whatsup = WhatsupSummary(
        summary="Pepe rallies on Binance perp listing rumours; retail piling in.",
        supportive=[
            WhatsupTheme(
                title="Listing speculation",
                description="Binance perp listing rumours fuel rally",
                percent=55.0,
            )
        ],
        critical=[
            WhatsupTheme(
                title="Overheat risk",
                description="Sentiment near contrarian territory",
                percent=20.0,
            )
        ],
    )
    pepe_news = [
        LunarCrushNewsItem(
            id="n1",
            post_title="Binance lists PEPE perp 50x",
            post_link="https://example.com",
            post_created=now - timedelta(hours=6),
            post_sentiment=4.2,
            creator_name="CoinDesk",
            creator_followers=500000,
            interactions_24h=12000,
        )
    ]
    pepe_posts = [
        LunarCrushPost(
            id="p1",
            post_type="tweet",
            post_title="PEPE to the moon",
            post_link="https://x.com/x",
            post_created=now - timedelta(hours=2),
            post_sentiment=4.5,
            creator_name="cryptoking",
            creator_display_name="Crypto King",
            creator_followers=500000,
            interactions_24h=20000,
        )
    ]
    pepe_ts = [
        CoinTimeSeriesPoint(time=now - timedelta(days=i), posts_active=4500 - i * 200)
        for i in range(7, 0, -1)
    ] + [CoinTimeSeriesPoint(time=now, posts_active=15000)]

    screener_pepe = ScreenerResult(
        symbol="1000PEPE/USDT:USDT",
        gate_passed=True,
        score=7,
        adx=28.4,
        direction="long",
        signals=empty_signals(),
    )

    insight_pepe = derive_social_insight(
        lc=lc_pepe,
        news=pepe_news,
        posts=pepe_posts,
        whatsup=whatsup,
        time_series=pepe_ts,
        screener_direction="long",
        now=now,
    )

    screener_silent = ScreenerResult(
        symbol="DOGE/USDT:USDT",
        gate_passed=True,
        score=4,
        adx=22.0,
        direction="short",
        signals=empty_signals(),
    )
    insight_silent = derive_social_insight(
        lc=None,
        news=[],
        posts=[],
        whatsup=None,
        time_series=[],
        screener_direction="short",
        now=now,
    )

    candidates = [
        EnrichedCandidate(
            symbol="1000PEPE/USDT:USDT",
            screener=screener_pepe,
            social=insight_pepe,
            enriched_at=now,
        ),
        EnrichedCandidate(
            symbol="DOGE/USDT:USDT",
            screener=screener_silent,
            social=insight_silent,
            enriched_at=now,
        ),
    ]
    return EnrichmentResult(candidates=candidates, macro=macro, fear_greed=64)
