from __future__ import annotations

import logging

import ccxt.async_support as ccxt

from app.clients.ccxt.models import FundingRateHistoryEntry, OHLCVCandle
from app.core import settings

logger = logging.getLogger(__name__)

_EXCHANGE_OPTIONS: dict[str, dict[str, str]] = {"options": {"defaultType": "swap"}}


def make_exchange(exchange_id: str = settings.EXCHANGE_ID) -> ccxt.Exchange:
    return getattr(ccxt, exchange_id)(_EXCHANGE_OPTIONS)


class CcxtClient:
    """Async клиент CCXT для OHLCV и funding rate. Использовать как async context manager.

    Создаёт один exchange на весь скринер и загружает markets один раз,
    вместо нового exchange на каждый API-вызов.
    """

    def __init__(self, exchange_id: str = settings.EXCHANGE_ID) -> None:
        self._exchange_id = exchange_id

    async def __aenter__(self) -> CcxtClient:
        self._exchange = make_exchange(self._exchange_id)
        try:
            await self._exchange.load_markets()
        except Exception:
            await self._exchange.close()
            raise
        return self

    async def __aexit__(self, *_: object) -> None:
        await self._exchange.close()

    async def fetch_ohlcv(
        self, symbol: str, timeframe: str = "4h", limit: int = 100
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
        self, symbol: str, limit: int = 21
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
