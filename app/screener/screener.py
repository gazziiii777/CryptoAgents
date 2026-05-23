from __future__ import annotations

import asyncio
import logging

from app.clients.binance.client import BinanceClient
from app.clients.ccxt.client import CcxtClient
from app.clients.coinglass.client import CoinGlassAuthError, CoinGlassClient
from app.core import settings
from app.screener.criteria import ScreenerResult, evaluate_symbol
from app.screener.universe import get_liquid_perp_pairs

logger = logging.getLogger(__name__)


async def _evaluate_guarded(
    symbol: str,
    semaphore: asyncio.Semaphore,
    ccxt_client: CcxtClient,
    binance_client: BinanceClient,
    cg_client: CoinGlassClient,
) -> ScreenerResult:
    async with semaphore:
        return await evaluate_symbol(symbol, ccxt_client, binance_client, cg_client)


async def run_screener() -> list[ScreenerResult]:
    """Полный прогон скринера по юниверсу.

    Шаги: получить юниверс → параллельно оценить каждую пару (с лимитом параллелизма)
    → отфильтровать по gate и score → вернуть топ-N отсортированных по score.
    """
    symbols = await get_liquid_perp_pairs()
    logger.info("Screener: evaluating %d symbols", len(symbols))

    semaphore = asyncio.Semaphore(settings.SCREENER_CONCURRENCY)
    async with (
        CcxtClient() as ccxt_client,
        BinanceClient() as binance_client,
        CoinGlassClient() as cg_client,
    ):
        raw_results = await asyncio.gather(
            *[
                _evaluate_guarded(s, semaphore, ccxt_client, binance_client, cg_client)
                for s in symbols
            ],
            return_exceptions=True,
        )

    results: list[ScreenerResult] = []
    for symbol, r in zip(symbols, raw_results):
        if isinstance(r, CoinGlassAuthError):
            raise r
        if isinstance(r, BaseException):
            logger.error("Screener: unhandled error for %s: %s", symbol, r)
            continue
        results.append(r)

    candidates = [
        r for r in results if r.gate_passed and r.score >= settings.SCREENER_MIN_SCORE
    ]
    candidates.sort(key=lambda r: r.score, reverse=True)
    top = candidates[: settings.SCREENER_TOP_N]

    logger.info(
        "Screener: %d/%d passed gate+score, returning top %d",
        len(candidates),
        len(symbols),
        len(top),
    )
    return top
