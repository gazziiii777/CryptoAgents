import logging
from typing import Self

import httpx

from app.adapters.clients._shared.errors import log_api_error, log_key_status
from app.adapters.clients._shared.rate_limiter import RateLimiter
from app.adapters.clients.lunarcrush.models import (
    CoinTimeSeriesPoint,
    LunarCrushCoinMetrics,
    LunarCrushNewsItem,
    LunarCrushPost,
    WhatsupSummary,
)
from core.settings import settings
from core.symbols import normalized_base

logger = logging.getLogger(__name__)

_SERVICE = "LunarCrush"
_BASE_URL = "https://lunarcrush.com/api4/public"
_AI_BASE_URL = "https://lunarcrush.ai"

_LC_RATE_PER_MIN = 9


def _log_err(exc: BaseException, path: str) -> None:
    log_api_error(_SERVICE, exc, path=path)


def _topic_slug(raw_topic: str, fallback: str) -> str:
    """LunarCrush topic-слаг для /topic/* запросов.

    Поле `topic` из /coins/list имеет формат «<symbol> <name…>» (напр.
    «btc bitcoin», «near near protocol»). Слаг = имя без ведущего символа:
    «btc bitcoin» → «bitcoin», «near near protocol» → «near protocol».
    Односложный topic берём как есть, пустой → fallback.
    """
    parts = raw_topic.split()
    if len(parts) > 1:
        return " ".join(parts[1:])
    if parts:
        return parts[0]
    return fallback


class LunarCrushClient:
    """Клиент LunarCrush API v4 + lunarcrush.ai. Использовать как async context manager.

    Стратегия: один батч-запрос /coins/list/v1 на весь прогон + per-symbol
    запросы /topic/{topic}/{whatsup,news,posts}/v1, /coins/{coin}/time-series/v2
    и lunarcrush.ai/topic/{topic} для каждого кандидата.

    Все запросы serialized через единый RateLimiter (_LC_RATE_PER_MIN req/min),
    чтобы не превышать лимит плана (10 req/min shared между api4 и lunarcrush.ai).

    При отсутствии LUNARCRUSH_API_KEY клиент работает в degraded-режиме и
    возвращает None/[] на все вызовы.
    """

    def __init__(self) -> None:
        log_key_status(_SERVICE, settings.LUNARCRUSH_API_KEY)
        self._enabled = bool(settings.LUNARCRUSH_API_KEY)
        if not self._enabled:
            self._http: httpx.AsyncClient | None = None
            self._http_ai: httpx.AsyncClient | None = None
            self._rate_limiter: RateLimiter | None = None
            return
        headers = {"Authorization": f"Bearer {settings.LUNARCRUSH_API_KEY}"}
        self._http = httpx.AsyncClient(
            base_url=_BASE_URL, headers=headers, timeout=settings.HTTP_TIMEOUT_S
        )
        self._http_ai = httpx.AsyncClient(
            base_url=_AI_BASE_URL, headers=headers, timeout=settings.HTTP_TIMEOUT_S
        )
        self._rate_limiter = RateLimiter(_LC_RATE_PER_MIN)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._http is not None:
            await self._http.aclose()
        if self._http_ai is not None:
            await self._http_ai.aclose()

    async def _acquire(self) -> None:
        if self._rate_limiter is not None:
            await self._rate_limiter.acquire()

    async def fetch_topic_metrics(
        self, symbols: list[str]
    ) -> dict[str, LunarCrushCoinMetrics]:
        """Метрики по символам через /coins/list/v1 (galaxy_score, sentiment, categories).

        Topic-slug для /topic/* считается через _topic_slug (имя без символа-префикса).
        Возвращает {normalized_symbol: metrics}.
        """
        if self._http is None or not symbols:
            return {}

        await self._acquire()
        try:
            resp = await self._http.get(
                "/coins/list/v1", params={"limit": settings.LUNARCRUSH_LIST_LIMIT}
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            _log_err(exc, "/coins/list/v1")
            return {}

        raw_items = resp.json().get("data") or []
        logger.debug("LunarCrush coins/list: %d coins returned", len(raw_items))

        if not raw_items:
            logger.warning("LunarCrush coins/list returned empty data")
            return {}

        symbol_to_coin: dict[str, dict[str, object]] = {
            str(item.get("symbol") or "").upper(): item for item in raw_items
        }

        result: dict[str, LunarCrushCoinMetrics] = {}
        for sym_raw in symbols:
            base = normalized_base(sym_raw)
            item = symbol_to_coin.get(base)
            if item is None:
                continue
            raw_topic = str(item.get("topic") or "")
            topic_slug = _topic_slug(raw_topic, base.lower())
            result[base] = LunarCrushCoinMetrics.model_validate({
                **item,
                "symbol": base,
                "topic": topic_slug,
            })

        missing = {normalized_base(s) for s in symbols} - set(result.keys())
        if missing:
            logger.debug(
                "LunarCrush: %d/%d symbols missing from coins/list: %s",
                len(missing),
                len(symbols),
                sorted(missing),
            )
        return result

    async def fetch_topic_whatsup(self, topic: str) -> WhatsupSummary | None:
        """AI-summary что обсуждается по топику. Возвращает None при ошибке.

        Требует Builder-план LunarCrush. По умолчанию отключён через
        LUNARCRUSH_WHATSUP_ENABLED=false — нарратив и темы покрываются
        lunarcrush.ai/topic/{topic} (lc_context).
        """
        if self._http is None or not topic:
            return None
        await self._acquire()
        try:
            resp = await self._http.get(f"/topic/{topic}/whatsup/v1")
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            _log_err(exc, f"/topic/{topic}/whatsup/v1")
            return None

        payload = resp.json()
        if not payload.get("summary"):
            return None
        return WhatsupSummary.model_validate(payload)

    async def fetch_topic_news(
        self, topic: str, limit: int | None = None
    ) -> list[LunarCrushNewsItem]:
        """Топ-новости по топику, уже отсортированные по социальной обсуждаемости."""
        if self._http is None or not topic:
            return []
        await self._acquire()
        try:
            resp = await self._http.get(f"/topic/{topic}/news/v1")
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            _log_err(exc, f"/topic/{topic}/news/v1")
            return []

        items = resp.json().get("data") or []
        news_limit = limit if limit is not None else settings.LUNARCRUSH_NEWS_LIMIT
        return [LunarCrushNewsItem.model_validate(item) for item in items[:news_limit]]

    async def fetch_topic_posts(
        self, topic: str, limit: int | None = None
    ) -> list[LunarCrushPost]:
        """Топ-посты по топику. creator_followers нужен для retail/influencer split."""
        if self._http is None or not topic:
            return []
        await self._acquire()
        try:
            resp = await self._http.get(f"/topic/{topic}/posts/v1")
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            _log_err(exc, f"/topic/{topic}/posts/v1")
            return []

        items = resp.json().get("data") or []
        posts_limit = limit if limit is not None else settings.LUNARCRUSH_POSTS_LIMIT
        return [LunarCrushPost.model_validate(item) for item in items[:posts_limit]]

    async def fetch_coin_time_series(
        self, coin: str, bucket: str = "day", interval: str = "1w"
    ) -> list[CoinTimeSeriesPoint]:
        """Time-series по монете для расчёта baseline.

        По умолчанию: дневные точки за неделю — достаточно для baseline-расчёта
        attention_level (среднее posts_active за 7 дней).
        """
        if self._http is None or not coin:
            return []
        await self._acquire()
        try:
            resp = await self._http.get(
                f"/coins/{coin}/time-series/v2",
                params={"bucket": bucket, "interval": interval},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            _log_err(exc, f"/coins/{coin}/time-series/v2")
            return []

        items = resp.json().get("data") or []
        return [CoinTimeSeriesPoint.model_validate(item) for item in items]

    async def fetch_topic_ai_context(self, topic: str) -> str | None:
        """LLM-оптимизированный markdown-контекст по топику от lunarcrush.ai.

        Возвращает richtext с engagements/mentions по сетям (TikTok/Instagram/
        Reddit/YouTube/X), таблицей топ-инфлюенсеров, историей sentiment/galaxy/
        altrank за 1w/1m/3m/1y и supportive/critical темами. Формат готов для
        прямой передачи LLM без дополнительной обработки.
        """
        if self._http_ai is None or not topic:
            return None
        await self._acquire()
        try:
            resp = await self._http_ai.get(f"/topic/{topic}")
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            _log_err(exc, f"/topic/{topic} (lunarcrush.ai)")
            return None
        text = resp.text
        return text if text else None
