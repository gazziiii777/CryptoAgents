import logging
from typing import Any, Self

from binance import AsyncClient
from binance.exceptions import BinanceAPIException

from app.adapters.clients.binance.models import CVDPoint, LongShortRatio, OISnapshot
from core.constants.time import (
    HOURS_PER_DAY,
    MINUTES_PER_HOUR,
    MS_PER_SECOND,
    SECONDS_PER_MINUTE,
)
from core.settings import settings
from core.symbols import to_exchange_pair

logger = logging.getLogger(__name__)

_MINUTE_MS = SECONDS_PER_MINUTE * MS_PER_SECOND
_HOUR_MS = MINUTES_PER_HOUR * _MINUTE_MS
_DAY_MS = HOURS_PER_DAY * _HOUR_MS

_INTERVAL_MAP: dict[int, str] = {
    5 * _MINUTE_MS: "5m",
    15 * _MINUTE_MS: "15m",
    _HOUR_MS: "1h",
    4 * _HOUR_MS: "4h",
    _DAY_MS: "1d",
}

_DEFAULT_CVD_TIMEFRAME_MS = 4 * _HOUR_MS
_DEFAULT_CVD_INTERVAL = "4h"

_KLINE_OPEN_TIME_IDX = 0
_KLINE_VOLUME_IDX = 5
_KLINE_TAKER_BUY_BASE_IDX = 9


def _resolve_cvd_interval(timeframe_ms: int) -> str:
    interval = _INTERVAL_MAP.get(timeframe_ms)
    if interval is None:
        logger.warning(
            "cvd: unknown timeframe_ms=%d, defaulting to %s",
            timeframe_ms,
            _DEFAULT_CVD_INTERVAL,
        )
        return _DEFAULT_CVD_INTERVAL
    return interval


def _klines_to_cvd(raw: list[list[Any]]) -> list[CVDPoint]:
    result: list[CVDPoint] = []
    cumulative = 0.0
    for candle in raw:
        total_vol = float(candle[_KLINE_VOLUME_IDX])
        buy_vol = float(candle[_KLINE_TAKER_BUY_BASE_IDX])
        cumulative += buy_vol - (total_vol - buy_vol)
        result.append(
            CVDPoint(timestamp=int(candle[_KLINE_OPEN_TIME_IDX]), cvd=cumulative)
        )
    return result


class BinanceClient:
    """Async клиент Binance FAPI/SAPI. Использовать как async context manager.

    async with BinanceClient() as client:
        oi = await client.fetch_open_interest_history("BTC/USDT:USDT")
    """

    async def __aenter__(self) -> Self:
        self._client = await AsyncClient.create(
            requests_params={"timeout": settings.HTTP_TIMEOUT_S}
        )
        return self

    async def __aexit__(self, *_: object) -> None:
        await self._client.close_connection()

    async def fetch_open_interest_history(
        self, symbol: str, period: str = "4h", limit: int = settings.OI_HISTORY_LIMIT
    ) -> list[OISnapshot]:
        """История OI. Binance FAPI /openInterest/hist, один запрос на limit точек."""
        binance_symbol = to_exchange_pair(symbol)
        raw = await self._client.futures_open_interest_hist(
            symbol=binance_symbol, period=period, limit=limit
        )
        return [OISnapshot.model_validate(item) for item in raw]

    async def fetch_long_short_ratio(
        self, symbol: str, period: str = "4h", limit: int = settings.LS_RATIO_LIMIT
    ) -> list[LongShortRatio]:
        """L/S ratio. Binance FAPI /globalLongShortAccountRatio."""
        binance_symbol = to_exchange_pair(symbol)
        raw = await self._client.futures_global_longshort_ratio(
            symbol=binance_symbol, period=period, limit=limit
        )
        return [LongShortRatio.model_validate(item) for item in raw]

    async def fetch_cvd(
        self,
        symbol: str,
        timeframe_ms: int = _DEFAULT_CVD_TIMEFRAME_MS,
        num_candles: int = settings.CVD_CANDLES,
    ) -> list[CVDPoint]:
        """CVD по фьючерсным свечам: Σ(buy_vol - sell_vol). cvd > 0 — байеры доминируют.

        buy_vol = takerBuyBaseAssetVolume, sell_vol = volume - takerBuyBase.
        Futures API: охватывает все перп-символы, в т.ч. те которых нет на споте.
        """
        raw = await self._client.futures_klines(
            symbol=to_exchange_pair(symbol),
            interval=_resolve_cvd_interval(timeframe_ms),
            limit=num_candles,
        )
        return _klines_to_cvd(raw)

    async def fetch_spot_cvd(
        self,
        symbol: str,
        timeframe_ms: int = _DEFAULT_CVD_TIMEFRAME_MS,
        num_candles: int = settings.CVD_CANDLES,
    ) -> list[CVDPoint]:
        """Spot-CVD по спот-свечам Binance — для сравнения с перп-потоком.

        Best-effort: у части перпов нет спот-пары (BinanceAPIException) → []. Спот
        отражает реальное накопление/распределение, перп — позиционирование ритейла.
        """
        try:
            raw = await self._client.get_klines(
                symbol=to_exchange_pair(symbol),
                interval=_resolve_cvd_interval(timeframe_ms),
                limit=num_candles,
            )
        except BinanceAPIException:
            return []
        except Exception:
            logger.warning(
                "fetch_spot_cvd: spot klines failed for %s, skipping spot signal",
                symbol,
                exc_info=True,
            )
            return []
        return _klines_to_cvd(raw)
