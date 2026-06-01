import asyncio
import logging
from datetime import UTC, datetime

import httpx

from app.clients.coingecko.client import CoinGeckoClient
from app.clients.coinglass.client import CoinGlassClient
from app.clients.lunarcrush.client import LunarCrushClient
from app.clients.lunarcrush.models import (
    CoinTimeSeriesPoint,
    LunarCrushCoinMetrics,
    LunarCrushNewsItem,
    LunarCrushPost,
    WhatsupSummary,
)
from app.enricher.insight import derive_social_insight
from app.models.enricher import EnrichedCandidate, EnrichmentResult
from app.models.screener import ScreenerResult
from core.settings import settings
from core.symbols import normalized_base

logger = logging.getLogger(__name__)


class DataEnricher:
    """Обогащает кандидатов скринера данными LunarCrush + макро CoinGecko.

    LunarCrush полностью покрывает социалку и новости: индексирует
    Twitter+Reddit+Telegram+TikTok+YouTube в крипто-контексте, считает
    sentiment, отдаёт AI-narrative и топ-посты с creator_followers.
    CryptoPanic и Twitter v2 не используются — лишние зависимости при
    полностью аналогичном покрытии.

    Для каждого кандидата параллельно фетчатся 4 LC-endpoint'а:
      - whatsup: AI-summary что обсуждается + supportive/critical темы
      - news: топ-новости отсортированные по социальной обсуждаемости
      - posts: топ-посты с creator_followers (retail vs influencer split)
      - time_series: baseline за неделю для корректного attention_level
    """

    async def enrich(self, candidates: list[ScreenerResult]) -> EnrichmentResult:
        """Один прогон: батч-coins/list + per-symbol whatsup/news/posts/ts."""
        symbols = [c.symbol for c in candidates]

        async with (
            CoinGeckoClient() as coingecko,
            CoinGlassClient() as coinglass,
            LunarCrushClient() as lunarcrush,
        ):
            macro, fear_greed, lc_metrics = await asyncio.gather(
                coingecko.fetch_macro_snapshot(),
                self._fetch_fear_greed(coinglass),
                lunarcrush.fetch_topic_metrics(symbols),
            )
            per_symbol = await asyncio.gather(
                *[
                    self._fetch_per_symbol(lunarcrush, c.symbol, lc_metrics)
                    for c in candidates
                ],
                return_exceptions=True,
            )

        now = datetime.now(UTC)
        enriched: list[EnrichedCandidate] = []
        for candidate, per_result in zip(candidates, per_symbol):
            if isinstance(per_result, asyncio.CancelledError):
                raise per_result
            if isinstance(per_result, BaseException):
                logger.warning(
                    "Enricher: per-symbol fetch failed for %s: %s",
                    candidate.symbol,
                    per_result,
                )
                whatsup = None
                news: list[LunarCrushNewsItem] = []
                posts: list[LunarCrushPost] = []
                time_series: list[CoinTimeSeriesPoint] = []
                lc_context = None
            else:
                whatsup, news, posts, time_series, lc_context = per_result

            lc = lc_metrics.get(normalized_base(candidate.symbol))
            insight = derive_social_insight(
                lc=lc,
                news=news,
                posts=posts,
                whatsup=whatsup,
                time_series=time_series,
                screener_direction=candidate.direction,
                now=now,
            )
            enriched.append(
                EnrichedCandidate(
                    symbol=candidate.symbol,
                    screener=candidate,
                    social=insight,
                    lc_context=lc_context,
                    enriched_at=now,
                )
            )

        logger.info(
            "Enricher: %d candidates enriched, lc_list_coverage=%d/%d",
            len(enriched),
            len(lc_metrics),
            len(candidates),
        )
        return EnrichmentResult(candidates=enriched, macro=macro, fear_greed=fear_greed)

    async def _fetch_per_symbol(
        self,
        lunarcrush: LunarCrushClient,
        symbol: str,
        lc_metrics: dict[str, LunarCrushCoinMetrics],
    ) -> tuple[
        WhatsupSummary | None,
        list[LunarCrushNewsItem],
        list[LunarCrushPost],
        list[CoinTimeSeriesPoint],
        str | None,
    ]:
        """Параллельно дёргает 5 LC-endpoint'ов для одного символа.

        Topic-slug берём из coins/list. Если в coins/list символа нет —
        fallback на сам символ (lowercase). Это работает для большинства
        майнстрим-коинов; для long-tail может промахнуться.

        Каждый вызов проходит через общий RateLimiter (9 req/min), поэтому
        5 вызовов на символ идут последовательно внутри лимита.
        """
        base = normalized_base(symbol)
        lc = lc_metrics.get(base)
        topic = (lc.topic if lc and lc.topic else base).lower()
        coin_ref = base

        news, posts, time_series, lc_context = await asyncio.gather(
            lunarcrush.fetch_topic_news(topic),
            lunarcrush.fetch_topic_posts(topic),
            lunarcrush.fetch_coin_time_series(coin_ref, bucket="day", interval="1w"),
            lunarcrush.fetch_topic_ai_context(topic),
        )
        whatsup = (
            await lunarcrush.fetch_topic_whatsup(topic)
            if settings.LUNARCRUSH_WHATSUP_ENABLED
            else None
        )
        return whatsup, news, posts, time_series, lc_context

    async def _fetch_fear_greed(self, coinglass: CoinGlassClient) -> int | None:
        try:
            history = await coinglass.fetch_fear_greed_history()
        except (httpx.HTTPError, RuntimeError) as exc:
            logger.warning("Failed to fetch fear_greed: %s", exc)
            return None
        return int(history[-1].value) if history else None
