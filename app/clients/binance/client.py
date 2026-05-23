from __future__ import annotations

import logging

from binance import AsyncClient

from app.clients.binance.models import CVDPoint, LongShortRatio, OISnapshot
from core import settings
from core.symbols import to_exchange_pair

logger = logging.getLogger(__name__)

_INTERVAL_MAP: dict[int, str] = {
    5 * 60 * 1000: "5m",
    15 * 60 * 1000: "15m",
    60 * 60 * 1000: "1h",
    4 * 60 * 60 * 1000: "4h",
    24 * 60 * 60 * 1000: "1d",
}


class BinanceClient:
    """Async клиент Binance FAPI/SAPI. Использовать как async context manager.

    async with BinanceClient() as client:
        oi = await client.fetch_open_interest_history("BTC/USDT:USDT")
    """

    async def __aenter__(self) -> BinanceClient:
        self._client = await AsyncClient.create(
            requests_params={"timeout": settings.HTTP_TIMEOUT_S}
        )
        return self

    async def __aexit__(self, *_: object) -> None:
        await self._client.close_connection()

    async def fetch_open_interest_history(
        self, symbol: str, period: str = "4h", limit: int = settings.OI_HISTORY_LIMIT
    ) -> list[OISnapshot]:
        """История OI. Binance FAPI /openInterest/hist, надёжная пагинация до 500 точек."""
        binance_symbol = to_exchange_pair(symbol)
        raw = await self._client.futures_open_interest_hist(
            symbol=binance_symbol, period=period, limit=limit
        )
        return [
            OISnapshot(
                timestamp=int(item["timestamp"]),
                open_interest=float(item["sumOpenInterest"]),
                open_interest_value=float(item["sumOpenInterestValue"]),
            )
            for item in raw
        ]

    async def fetch_long_short_ratio(
        self, symbol: str, period: str = "4h", limit: int = settings.LS_RATIO_LIMIT
    ) -> list[LongShortRatio]:
        """L/S ratio. Binance FAPI /globalLongShortAccountRatio."""
        binance_symbol = to_exchange_pair(symbol)
        raw = await self._client.futures_global_longshort_ratio(
            symbol=binance_symbol, period=period, limit=limit
        )
        return [
            LongShortRatio(
                timestamp=int(item["timestamp"]),
                long_short_ratio=float(item["longShortRatio"]),
                long_account=float(item["longAccount"]),
                short_account=float(item["shortAccount"]),
            )
            for item in raw
        ]

    async def fetch_cvd(
        self,
        symbol: str,
        timeframe_ms: int = 4 * 60 * 60 * 1000,
        num_candles: int = settings.CVD_CANDLES,
    ) -> list[CVDPoint]:
        """CVD по фьючерсным свечам: Σ(buy_vol - sell_vol). cvd > 0 — байеры доминируют.

        buy_vol = takerBuyBaseAssetVolume, sell_vol = volume - takerBuyBase.
        Futures API: охватывает все перп-символы, в т.ч. те которых нет на споте.
        """
        futures_symbol = to_exchange_pair(symbol)
        interval = _INTERVAL_MAP.get(timeframe_ms)
        if interval is None:
            logger.warning(
                "fetch_cvd: unknown timeframe_ms=%d, defaulting to 4h", timeframe_ms
            )
            interval = "4h"

        raw = await self._client.futures_klines(
            symbol=futures_symbol, interval=interval, limit=num_candles
        )

        result = []
        cumulative = 0.0
        for candle in raw:
            total_vol = float(candle[5])
            buy_vol = float(candle[9])
            cumulative += buy_vol * 2 - total_vol
            result.append(CVDPoint(timestamp=int(candle[0]), cvd=cumulative))

        return result
