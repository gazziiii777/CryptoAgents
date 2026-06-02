import asyncio
import logging
from typing import Any

from app.clients.ccxt.client import make_exchange
from app.clients.ccxt.models import CcxtMarket, CcxtTicker
from core.constants.markets import EXCLUDED_BASE_SYMBOLS
from core.settings import settings

logger = logging.getLogger(__name__)

_CRYPTO_UNDERLYING_TYPE = "COIN"


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
    markets: dict[str, dict[str, Any]],
    tickers: dict[str, dict[str, Any]],
    quote_currency: str,
    min_volume_usd: float,
) -> list[str]:
    scored: list[tuple[str, float]] = []

    for symbol, ticker_raw in tickers.items():
        market_raw = markets.get(symbol)
        if market_raw is None:
            continue
        market = CcxtMarket.model_validate(market_raw)
        if not market.swap or market.quote != quote_currency or not market.active:
            continue
        if market.underlying_type != _CRYPTO_UNDERLYING_TYPE:
            continue
        if (
            not market.base
            or not market.base.isascii()
            or market.base in EXCLUDED_BASE_SYMBOLS
        ):
            continue

        volume_usd = CcxtTicker.model_validate(ticker_raw).quote_volume or 0.0
        if volume_usd < min_volume_usd:
            continue

        scored.append((symbol, volume_usd))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [symbol for symbol, _ in scored]
