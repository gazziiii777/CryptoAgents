import logging
from typing import Self

import ccxt.async_support as ccxt

from app.clients.ccxt.models import (
    FundingRateHistoryEntry,
    OHLCVCandle,
    OrderBook,
    OrderBookLevel,
)
from core.constants.time import MS_PER_SECOND
from core.settings import settings

logger = logging.getLogger(__name__)

_DEFAULT_MARKET_TYPE = "swap"
_HTTP_TIMEOUT_MS = int(settings.HTTP_TIMEOUT_S * MS_PER_SECOND)
_DEFAULT_OHLCV_LIMIT = 100


def make_exchange(exchange_id: str = settings.EXCHANGE_ID) -> ccxt.Exchange:
    return getattr(ccxt, exchange_id)({
        "options": {"defaultType": _DEFAULT_MARKET_TYPE},
        "timeout": _HTTP_TIMEOUT_MS,
    })


class CcxtClient:
    """Async клиент CCXT для OHLCV и funding rate. Использовать как async context manager.

    Создаёт один exchange на весь скринер и загружает markets один раз,
    вместо нового exchange на каждый API-вызов.
    """

    def __init__(self, exchange_id: str = settings.EXCHANGE_ID) -> None:
        self._exchange_id = exchange_id

    async def __aenter__(self) -> Self:
        self._exchange = make_exchange(self._exchange_id)
        try:
            await self._exchange.load_markets()
        except ccxt.BaseError as exc:
            logger.error(
                "CCXT load_markets failed for exchange %s: %s", self._exchange_id, exc
            )
            await self._exchange.close()
            raise
        return self

    async def __aexit__(self, *_: object) -> None:
        await self._exchange.close()

    async def fetch_ohlcv(
        self, symbol: str, timeframe: str = "4h", limit: int = _DEFAULT_OHLCV_LIMIT
    ) -> list[OHLCVCandle]:
        """Загрузить OHLCV свечи. Binance: максимум 1500 за запрос, результат старые → новые."""
        raw = await self._exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        return [
            OHLCVCandle(
                timestamp=int(row[0]),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
            )
            for row in raw
        ]

    async def fetch_funding_rate_history(
        self, symbol: str, limit: int = settings.FUNDING_HISTORY_LIMIT
    ) -> list[FundingRateHistoryEntry]:
        """История ставок финансирования. Binance: записи с шагом 8h, limit=21 ≈ 7 дней."""
        raw = await self._exchange.fetch_funding_rate_history(symbol, limit=limit)
        return [
            FundingRateHistoryEntry(
                timestamp=int(record["timestamp"]),
                funding_rate=float(record["fundingRate"]),
            )
            for record in raw
        ]

    async def fetch_order_book(
        self, symbol: str, depth: int = settings.LIQUIDITY_ORDERBOOK_DEPTH
    ) -> OrderBook:
        """L2-стакан: bids/asks как [price, amount], отсортированы от лучшей цены."""
        raw = await self._exchange.fetch_order_book(symbol, limit=depth)
        return OrderBook(
            bids=[
                OrderBookLevel(price=float(price), amount=float(amount))
                for price, amount in raw["bids"]
            ],
            asks=[
                OrderBookLevel(price=float(price), amount=float(amount))
                for price, amount in raw["asks"]
            ],
        )
