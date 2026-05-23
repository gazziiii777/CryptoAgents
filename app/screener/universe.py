from __future__ import annotations

import asyncio
import logging


from app.clients.ccxt.client import make_exchange
from app.core import settings

logger = logging.getLogger(__name__)


async def get_liquid_perp_pairs(
    exchange_id: str = settings.EXCHANGE_ID,
    quote_currency: str = settings.QUOTE_CURRENCY,
    min_volume_usd: float = settings.UNIVERSE_MIN_VOLUME_USD,
) -> list[str]:
    """Ликвидные перп-пары биржи, отфильтрованные по quote и объёму, отсортированные по объёму убыванием.

    Формат символов: ccxt, например ["BTC/USDT:USDT", "ETH/USDT:USDT", ...].
    """
    exchange = make_exchange(exchange_id)
    try:
        markets, tickers = await asyncio.gather(
            exchange.load_markets(), exchange.fetch_tickers()
        )
        candidates = _filter_perp_pairs(
            markets, tickers, quote_currency, min_volume_usd
        )
        logger.info(
            "Universe: %d pairs pass filters (exchange=%s, min_vol=$%.0f)",
            len(candidates),
            exchange_id,
            min_volume_usd,
        )
        return candidates
    finally:
        await exchange.close()


def _filter_perp_pairs(
    markets: dict, tickers: dict, quote_currency: str, min_volume_usd: float
) -> list[str]:
    scored: list[tuple[str, float]] = []

    for symbol, ticker in tickers.items():
        market = markets.get(symbol)
        if market is None:
            continue
        if not market["swap"]:
            continue
        if market["quote"] != quote_currency:
            continue
        if not market["active"]:
            continue

        volume_usd = ticker["quoteVolume"] or 0.0
        if volume_usd < min_volume_usd:
            continue

        scored.append((symbol, volume_usd))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [symbol for symbol, _ in scored]
