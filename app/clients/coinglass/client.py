from __future__ import annotations

import asyncio
import logging
from enum import IntEnum
from typing import Any

import httpx

from app.clients._shared.errors import log_api_error, log_key_status
from app.clients._shared.rate_limiter import RateLimiter
from app.clients.coinglass.models import (
    AggregatedCVDPoint,
    AltcoinSeasonPoint,
    FearGreedPoint,
    FundingRateOHLC,
    FuturesBasisPoint,
    FuturesSpotRatioPoint,
    LargeOrderEntry,
    LiquidationHeatmapData,
    LiquidationHistoryPoint,
    MaxPainEntry,
    NetPositionPoint,
    OIAggregatedCandle,
    TokenUnlockEntry,
    TopPositionRatio,
)
from app.core import settings
from app.core.symbols import base_currency, to_exchange_pair

logger = logging.getLogger(__name__)

_SERVICE = "CoinGlass"
_BASE_URL = "https://open-api-v4.coinglass.com"

_AGG_EXCHANGE_LIST = "Binance,OKX,Bybit"
_RATE_LIMIT_PAUSE_S = 120
_MAX_CONCURRENT = 2


class CoinGlassPlanRate(IntEnum):
    """Безопасный rate-limit (req/min) по тарифу CoinGlass.

    Значения — реальный лимит тарифа минус ~7% запаса, чтобы leaky-bucket
    лимитер не упирался в 429 на bursts. Активный тариф определяется флагами
    COINGLASS_*_PLAN в settings.
    """

    HOBBYIST = 28  # real 30 req/min  ($29-35/mo)
    STARTUP = 76  # real 80 req/min  ($79-95/mo)
    STANDARD = 285  # real 300 req/min ($299-379/mo)
    PROFESSIONAL = 1140  # real 1200 req/min ($699-879/mo)


def _resolve_rate_per_minute() -> int:
    """Лимит на минуту по активному тарифу CoinGlass.

    Переключение тарифа в .env через COINGLASS_*_PLAN автоматически подтягивает
    соответствующий лимит из CoinGlassPlanRate без правок кода.
    """
    if settings.COINGLASS_PROFESSIONAL_PLAN:
        return CoinGlassPlanRate.PROFESSIONAL
    if settings.COINGLASS_STANDARD_PLAN:
        return CoinGlassPlanRate.STANDARD
    if settings.COINGLASS_STARTUP_PLAN:
        return CoinGlassPlanRate.STARTUP
    return CoinGlassPlanRate.HOBBYIST


_CG_RATE_PER_MINUTE = _resolve_rate_per_minute()


class CoinGlassAuthError(RuntimeError):
    """API key is missing, invalid, or has insufficient permissions."""


class CoinGlassClient:
    """Async клиент CoinGlass API. Использовать как async context manager.

    async with CoinGlassClient() as client:
        oi = await client.fetch_oi_aggregated_history("BTC/USDT:USDT")
    """

    def __init__(self) -> None:
        log_key_status(_SERVICE, settings.COINGLASS_API_KEY)
        if not settings.COINGLASS_API_KEY:
            raise RuntimeError("COINGLASS_API_KEY env var is not set")
        self._http = httpx.AsyncClient(
            base_url=_BASE_URL,
            headers={"CG-API-KEY": settings.COINGLASS_API_KEY},
            timeout=settings.HTTP_TIMEOUT_S,
        )
        self._rate_limiter = RateLimiter(_CG_RATE_PER_MINUTE)
        self._sem = asyncio.Semaphore(_MAX_CONCURRENT)
        self._gate = asyncio.Event()
        self._gate.set()
        self._reopen_task: asyncio.Task[None] | None = None

    async def _reopen_gate(self) -> None:
        await asyncio.sleep(_RATE_LIMIT_PAUSE_S)
        self._gate.set()
        logger.info("CoinGlass rate limit pause lifted, resuming requests")

    async def close(self) -> None:
        if self._reopen_task and not self._reopen_task.done():
            self._reopen_task.cancel()
        await self._http.aclose()

    async def __aenter__(self) -> CoinGlassClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def _request(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        """HTTP GET: семафор → gate (пауза при rate limit) → leaky bucket → запрос."""
        async with self._sem:
            for attempt in range(3):
                await self._gate.wait()
                await self._rate_limiter.acquire()
                await self._gate.wait()

                resp = await self._http.get(path, params=params)
                if resp.status_code == 429:
                    msg = "Too Many Requests"
                else:
                    try:
                        resp.raise_for_status()
                    except httpx.HTTPStatusError as exc:
                        log_api_error(_SERVICE, exc, path=path)
                        if exc.response.status_code in (401, 403):
                            raise CoinGlassAuthError(
                                f"CoinGlass API key invalid or expired "
                                f"(HTTP {exc.response.status_code}) — check COINGLASS_API_KEY"
                            ) from exc
                        raise
                    body: dict[str, Any] = resp.json()
                    if body.get("code") == "0":
                        return body
                    msg = body.get("msg", "unknown")

                if "Too Many Requests" in msg:
                    if attempt < 2:
                        if self._gate.is_set():
                            self._gate.clear()
                            logger.warning(
                                "CoinGlass rate limit hit (attempt %d) — pausing ALL requests for %ds",
                                attempt + 1,
                                _RATE_LIMIT_PAUSE_S,
                            )
                            if self._reopen_task is None or self._reopen_task.done():
                                self._reopen_task = asyncio.create_task(
                                    self._reopen_gate()
                                )
                        await self._gate.wait()
                        continue
                    logger.error(
                        "CoinGlass rate limit persists after %d retries on %s — request dropped",
                        attempt,
                        path,
                    )
                    raise RuntimeError(
                        f"CoinGlass rate limited after {attempt} retries: {path}"
                    )
                raise RuntimeError(f"CoinGlass API error on {path}: {msg}")
            raise RuntimeError(f"CoinGlass API error on {path}: exhausted all retries")

    async def _get(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Для эндпоинтов где data — список объектов."""
        body = await self._request(path, params)
        data = body["data"]
        if not isinstance(data, list):
            raise RuntimeError(
                f"CoinGlass {path}: expected list in 'data', got {type(data).__name__}"
            )
        return data

    async def _get_obj(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        """Для эндпоинтов где data — dict, а не список."""
        body = await self._request(path, params)
        data = body["data"]
        if not isinstance(data, dict):
            raise RuntimeError(
                f"CoinGlass {path}: expected dict in 'data', got {type(data).__name__}"
            )
        return data

    async def fetch_oi_aggregated_history(
        self, symbol: str, interval: str = "4h", limit: int = settings.OI_HISTORY_LIMIT
    ) -> list[OIAggregatedCandle]:
        """Агрегированный OI по всем биржам в формате OHLC (USD).

        Покрывает Binance, OKX, Bybit, Deribit и др. — в отличие от Binance-only OI.
        """
        data = await self._get(
            "/api/futures/open-interest/aggregated-history",
            {
                "symbol": base_currency(symbol),
                "interval": interval,
                "limit": limit,
                "unit": "usd",
            },
        )
        return [
            OIAggregatedCandle(
                timestamp=int(item["time"]),
                open=float(item["open"]),
                high=float(item["high"]),
                low=float(item["low"]),
                close=float(item["close"]),
            )
            for item in data
        ]

    async def fetch_aggregated_cvd_history(
        self, symbol: str, interval: str = "4h", limit: int = settings.CVD_CANDLES
    ) -> list[AggregatedCVDPoint]:
        """Фьючерсный CVD агрегированный по биржам (Binance, OKX, Bybit).

        Требует Startup+ план CoinGlass. Возвращает [] если COINGLASS_STARTUP_PLAN=False.
        cvd_delta > 0 — байеры доминировали в интервале, < 0 — продавцы.
        """
        if not settings.COINGLASS_STARTUP_PLAN:
            logger.debug(
                "fetch_aggregated_cvd_history: requires Startup+ plan, set COINGLASS_STARTUP_PLAN=True to enable"
            )
            return []

        data = await self._get(
            "/api/futures/aggregated-cvd/history",
            {
                "exchange_list": _AGG_EXCHANGE_LIST,
                "symbol": base_currency(symbol),
                "interval": interval,
                "limit": limit,
                "unit": "usd",
            },
        )
        return [
            AggregatedCVDPoint(
                timestamp=int(item["time"]),
                agg_taker_buy_vol=float(item["agg_taker_buy_vol"]),
                agg_taker_sell_vol=float(item["agg_taker_sell_vol"]),
                cvd_delta=float(item["cum_vol_delta"]),
            )
            for item in data
        ]

    async def fetch_top_position_ratio(
        self,
        symbol: str,
        exchange: str = "Binance",
        interval: str = "4h",
        limit: int = settings.LS_RATIO_LIMIT,
    ) -> list[TopPositionRatio]:
        """L/S ratio топ-трейдеров по объёму позиций (не по количеству аккаунтов).

        Показывает куда направлен КАПИТАЛ крупных игроков, а не количество людей.
        Directional сигнал — следуем за smart money, в отличие от retail L/S (контрарный).
        """
        data = await self._get(
            "/api/futures/top-long-short-position-ratio/history",
            {
                "exchange": exchange,
                "symbol": to_exchange_pair(symbol),
                "interval": interval,
                "limit": limit,
            },
        )
        return [
            TopPositionRatio(
                timestamp=int(item["time"]),
                long_percent=float(item["top_position_long_percent"]),
                short_percent=float(item["top_position_short_percent"]),
                long_short_ratio=float(item["top_position_long_short_ratio"]),
            )
            for item in data
        ]

    async def fetch_funding_rate_oi_weight_history(
        self, symbol: str, interval: str = "4h", limit: int = settings.OI_HISTORY_LIMIT
    ) -> list[FundingRateOHLC]:
        """OI-взвешенная ставка финансирования по всем биржам в формате OHLC.

        Точнее однобиржевого funding rate из ccxt: взвешивает по открытому интересу,
        поэтому биржи с большим OI влияют сильнее. Доступен на всех планах (>=4h).
        """
        data = await self._get(
            "/api/futures/funding-rate/oi-weight-history",
            {"symbol": base_currency(symbol), "interval": interval, "limit": limit},
        )
        return [
            FundingRateOHLC(
                timestamp=int(item["time"]),
                open=float(item["open"]),
                high=float(item["high"]),
                low=float(item["low"]),
                close=float(item["close"]),
            )
            for item in data
        ]

    async def fetch_futures_basis_history(
        self,
        symbol: str,
        exchange: str = "Binance",
        interval: str = "4h",
        limit: int = settings.OI_HISTORY_LIMIT,
    ) -> list[FuturesBasisPoint]:
        """Исторический базис фьючерс vs спот (контанго/бэквордация).

        close_basis > 0 — фьючерс дороже спота (контанго, бычий сентимент).
        close_basis < 0 — бэквордация (давление продавцов, медвежий сентимент).
        Доступен на всех планах (>=4h).
        """
        data = await self._get(
            "/api/futures/basis/history",
            {
                "exchange": exchange,
                "symbol": to_exchange_pair(symbol),
                "interval": interval,
                "limit": limit,
            },
        )
        return [
            FuturesBasisPoint(
                timestamp=int(item["time"]),
                open_basis=float(item["open_basis"]),
                close_basis=float(item["close_basis"]),
                open_change=float(item["open_change"]),
                close_change=float(item["close_change"]),
            )
            for item in data
        ]

    async def fetch_net_position_history(
        self,
        symbol: str,
        exchange: str = "Binance",
        interval: str = "4h",
        limit: int = settings.OI_HISTORY_LIMIT,
    ) -> list[NetPositionPoint]:
        """Нетто-изменение позиций трейдеров за интервал (Startup+).

        net_long_change > 0 — новые лонги открыты; < 0 — лонги закрыты/ликвидированы.
        net_short_change > 0 — новые шорты открыты; < 0 — шорты закрыты/ликвидированы.
        Возвращает [] если COINGLASS_STARTUP_PLAN=False.
        """
        if not settings.COINGLASS_STARTUP_PLAN:
            logger.debug(
                "fetch_net_position_history: requires Startup+ plan, set COINGLASS_STARTUP_PLAN=True to enable"
            )
            return []

        data = await self._get(
            "/api/futures/net-position/history",
            {
                "exchange": exchange,
                "symbol": to_exchange_pair(symbol),
                "interval": interval,
                "limit": limit,
            },
        )
        return [
            NetPositionPoint(
                timestamp=int(item["time"]),
                net_long_change=float(item["net_long_change"]),
                net_short_change=float(item["net_short_change"]),
                net_position_change_cum=float(item["net_position_change_cum"]),
            )
            for item in data
        ]

    async def fetch_liquidation_heatmap(
        self, symbol: str, exchange: str = "Binance", range_: str = "3d"
    ) -> LiquidationHeatmapData:
        """Тепловая карта ликвидационных уровней по цене (Professional+).

        y_axis — ценовые уровни; liquidation_leverage_data — [[x_idx, y_idx, amount_usd]].
        Чтобы найти уровни с максимальным объёмом ликвидаций — суммировать amount_usd по y_idx.
        Возвращает пустую структуру если COINGLASS_PROFESSIONAL_PLAN=False.
        """
        if not settings.COINGLASS_PROFESSIONAL_PLAN:
            logger.debug(
                "fetch_liquidation_heatmap: requires Professional+ plan, set COINGLASS_PROFESSIONAL_PLAN=True to enable"
            )
            return LiquidationHeatmapData(y_axis=[], liquidation_leverage_data=[])

        raw = await self._get_obj(
            "/api/futures/liquidation/heatmap/model1",
            {"exchange": exchange, "symbol": to_exchange_pair(symbol), "range": range_},
        )
        return LiquidationHeatmapData(
            y_axis=[float(p) for p in raw["y_axis"]],
            liquidation_leverage_data=raw["liquidation_leverage_data"],
        )

    async def fetch_liquidation_max_pain(
        self, range_: str = "24h"
    ) -> list[MaxPainEntry]:
        """Цены максимальных ликвидаций по всем монетам (Professional+).

        Макро-эндпоинт: один вызов → данные по всем монетам, не per-symbol.
        long_max_pain_price — цена, при которой суммарный объём ликвидаций лонгов максимален.
        Возвращает [] если COINGLASS_PROFESSIONAL_PLAN=False.
        """
        if not settings.COINGLASS_PROFESSIONAL_PLAN:
            logger.debug(
                "fetch_liquidation_max_pain: requires Professional+ plan, set COINGLASS_PROFESSIONAL_PLAN=True to enable"
            )
            return []

        data = await self._get("/api/futures/liquidation/max-pain", {"range": range_})
        return [
            MaxPainEntry(
                symbol=item["symbol"],
                price=float(item["price"]),
                long_max_pain_price=float(item["long_max_pain_liq_price"]),
                long_max_pain_level=float(item["long_max_pain_liq_level"]),
                short_max_pain_price=float(item["short_max_pain_liq_price"]),
                short_max_pain_level=float(item["short_max_pain_liq_level"]),
            )
            for item in data
        ]

    async def fetch_large_orderbook(
        self, symbol: str, exchange: str = "Binance"
    ) -> list[LargeOrderEntry]:
        """Крупные лимитные ордера в стакане спот-рынка (Standard+).

        Снапшот текущего стакана: только ордера выше порога (BTC ≥ $350K, ETH ≥ $250K, прочие ≥ $10K).
        order_side=1 (Buy) — потенциальный уровень поддержки; order_side=2 (Sell) — сопротивление.
        Возвращает [] если COINGLASS_STANDARD_PLAN=False.
        """
        if not settings.COINGLASS_STANDARD_PLAN:
            logger.debug(
                "fetch_large_orderbook: requires Standard+ plan, set COINGLASS_STANDARD_PLAN=True to enable"
            )
            return []

        data = await self._get(
            "/api/spot/orderbook/large-limit-order",
            {"exchange": exchange, "symbol": to_exchange_pair(symbol)},
        )
        return [
            LargeOrderEntry(
                price=float(item["price"]),
                current_usd_value=float(item["current_usd_value"]),
                start_time=int(item["start_time"]),
                order_side=int(item["order_side"]),
                order_state=int(item["order_state"]),
            )
            for item in data
        ]

    async def fetch_fear_greed_history(self) -> list[FearGreedPoint]:
        """Исторический индекс страха/жадности (Fear & Greed).

        Макро-эндпоинт: один вызов за прогон, параметров нет. Обновляется раз в сутки.
        Ответ — параллельные массивы time_list/data_list/price_list в одном объекте.
        """
        data = await self._get("/api/index/fear-greed-history", {})
        if not data:
            return []
        entry = data[0]
        return [
            FearGreedPoint(timestamp=int(ts) * 1000, value=float(v), price=float(p))
            for ts, v, p in zip(
                entry["time_list"], entry["data_list"], entry["price_list"]
            )
        ]

    async def fetch_altcoin_season(self) -> list[AltcoinSeasonPoint]:
        """Исторический индекс сезона альткоинов (Startup+).

        Макро-эндпоинт: один вызов за прогон, параметров нет. Обновляется каждые 5 минут.
        >75 — altcoin season (альткоины опережают BTC), <25 — bitcoin season.
        Возвращает [] если COINGLASS_STARTUP_PLAN=False.
        """
        if not settings.COINGLASS_STARTUP_PLAN:
            logger.debug(
                "fetch_altcoin_season: requires Startup+ plan, set COINGLASS_STARTUP_PLAN=True to enable"
            )
            return []

        data = await self._get("/api/index/altcoin-season", {})
        return [
            AltcoinSeasonPoint(
                timestamp=int(item["timestamp"]),
                altcoin_index=int(item["altcoin_index"]),
            )
            for item in data
        ]

    async def fetch_futures_spot_volume_ratio(
        self, symbol: str, interval: str = "4h", limit: int = settings.OI_HISTORY_LIMIT
    ) -> list[FuturesSpotRatioPoint]:
        """Соотношение объёма фьючерсов к споту по символу (Startup+).

        futures_spot_vol_ratio >> 1 — спекулятивная активность доминирует над спотом.
        Возвращает [] если COINGLASS_STARTUP_PLAN=False.
        """
        if not settings.COINGLASS_STARTUP_PLAN:
            logger.debug(
                "fetch_futures_spot_volume_ratio: requires Startup+ plan, set COINGLASS_STARTUP_PLAN=True to enable"
            )
            return []

        data = await self._get(
            "/api/futures_spot_volume_ratio",
            {
                "exchange_list": _AGG_EXCHANGE_LIST,
                "symbol": base_currency(symbol),
                "interval": interval,
                "limit": limit,
            },
        )
        return [
            FuturesSpotRatioPoint(
                timestamp=int(item["time"]),
                futures_spot_vol_ratio=float(item["futures_spot_vol_ratio"]),
                futures_vol_usd=float(item["futures_vol_usd"]),
                spot_vol_usd=float(item["spot_vol_usd"]),
            )
            for item in data
        ]

    async def fetch_token_unlock_list(
        self, per_page: int = 100, page: int = 1
    ) -> list[TokenUnlockEntry]:
        """Расписание разблокировок токенов (Startup+).

        Макро-эндпоинт: один вызов за прогон. Возвращает токены отсортированные по дате разлока.
        next_unlock_of_circulating > 0.05 (>5% circulating) — потенциальное давление продаж.
        Возвращает [] если COINGLASS_STARTUP_PLAN=False.
        """
        if not settings.COINGLASS_STARTUP_PLAN:
            logger.debug(
                "fetch_token_unlock_list: requires Startup+ plan, set COINGLASS_STARTUP_PLAN=True to enable"
            )
            return []

        data = await self._get(
            "/api/coin/unlock-list", {"per_page": per_page, "page": page}
        )
        return [
            TokenUnlockEntry(
                symbol=item["symbol"],
                next_unlock_date=int(item["next_unlock_date"]),
                next_unlock_tokens=float(item["next_unlock_tokens"]),
                next_unlock_of_circulating=float(item["next_unlock_of_circulating"]),
            )
            for item in data
        ]

    async def fetch_liquidation_aggregated_history(
        self, symbol: str, interval: str = "4h", limit: int = settings.OI_HISTORY_LIMIT
    ) -> list[LiquidationHistoryPoint]:
        """История ликвидаций лонгов и шортов по монете агрегированно по биржам.

        Доступен на всех планах (Hobbyist >= 4h). Высокий long_liquidation_usd
        при падении цены = каскадные стоп-ауты, momentum вниз.
        """
        data = await self._get(
            "/api/futures/liquidation/aggregated-history",
            {
                "exchange_list": _AGG_EXCHANGE_LIST,
                "symbol": base_currency(symbol),
                "interval": interval,
                "limit": limit,
            },
        )
        return [
            LiquidationHistoryPoint(
                timestamp=int(item["time"]),
                long_liquidation_usd=float(item["aggregated_long_liquidation_usd"]),
                short_liquidation_usd=float(item["aggregated_short_liquidation_usd"]),
            )
            for item in data
        ]

    async def fetch_futures_large_orderbook(
        self, symbol: str, exchange: str = "Binance"
    ) -> list[LargeOrderEntry]:
        """Крупные лимитные ордера в фьючерсном стакане (Standard+).

        Аналог fetch_large_orderbook, но для фьючерсного рынка — релевантнее для перп-трейдинга.
        order_side=1 (Buy) — потенциальный уровень поддержки; order_side=2 (Sell) — сопротивление.
        Возвращает [] если COINGLASS_STANDARD_PLAN=False.
        """
        if not settings.COINGLASS_STANDARD_PLAN:
            logger.debug(
                "fetch_futures_large_orderbook: requires Standard+ plan, set COINGLASS_STANDARD_PLAN=True to enable"
            )
            return []

        data = await self._get(
            "/api/futures/orderbook/large-limit-order",
            {"exchange": exchange, "symbol": to_exchange_pair(symbol)},
        )
        return [
            LargeOrderEntry(
                price=float(item["price"]),
                current_usd_value=float(item["current_usd_value"]),
                start_time=int(item["start_time"]),
                order_side=int(item["order_side"]),
                order_state=int(item["order_state"]),
            )
            for item in data
        ]
