import asyncio
import logging

from app.clients.binance.client import BinanceClient
from app.clients.ccxt.client import CcxtClient
from app.clients.coinglass.client import CoinGlassClient
from app.clients.coinglass.exceptions import CoinGlassAuthError
from app.screener.evaluation import evaluate_symbol
from app.models.screener import ScreenerResult
from app.screener.universe import get_liquid_perp_pairs
from core.settings import settings

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


async def run_screener(limit: int | None = None) -> list[ScreenerResult]:
    """Полный прогон скринера по юниверсу.

    Шаги: получить юниверс → параллельно оценить каждую пару (с лимитом параллелизма)
    → отфильтровать по gate и score → вернуть топ-N отсортированных по score.

    limit — ограничить оценку топ-N пар по объёму (smoke/dev); None = весь юниверс.
    """
    symbols = await get_liquid_perp_pairs()
    if limit is not None:
        symbols = symbols[:limit]
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
            if not isinstance(r, Exception):
                raise r
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
