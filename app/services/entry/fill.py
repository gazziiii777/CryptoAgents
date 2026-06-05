import logging

import ccxt

from app.adapters.clients.ccxt.client import CcxtClient
from app.adapters.clients.ccxt.models import OHLCVCandle
from app.services.entry.models.fill_result import FillResult
from app.domain.synthesis.levelcomputer import resolve_setup
from app.domain.models.analysis import CandidateSignal
from app.domain.models.setup import FinalSignal, SetupIntent
from core.constants.decisions import (
    REASON_ENTRY_DRIFT,
    REASON_FILL_UNAVAILABLE,
    REASON_SIGNAL_READY,
    REASON_STALE_LEVELS,
)
from core.settings import settings

logger = logging.getLogger(__name__)


def evaluate_fill(
    intent: SetupIntent,
    final: FinalSignal,
    funding_rate: float,
    candles_4h: list[OHLCVCandle],
    candles_1d: list[OHLCVCandle],
) -> FillResult:
    """Чистое ядро филла: drift-гейт + пере-резолв уровней от живой цены (без IO).

    Живая цена — close последней (формирующейся) свечи. Если она ушла от snapshot-входа
    дальше MAX_ENTRY_DRIFT_PCT — сигнал отклоняется (не гонимся за убежавшим входом).
    Иначе SetupIntent резолвится заново той же resolve_setup от живой цены: стоп/цель
    пере-заякориваются, R/R сохраняется; confluence/тезис из исходного сигнала не меняются.
    """
    if not candles_4h or not candles_1d:
        return FillResult(None, REASON_STALE_LEVELS)
    live_price = candles_4h[-1].close
    drift = abs(live_price - final.entry_price) / final.entry_price
    if drift > settings.MAX_ENTRY_DRIFT_PCT:
        logger.info(
            "fill rejected: entry drift %.3f%% > %.3f%% (%s)",
            drift * 100,
            settings.MAX_ENTRY_DRIFT_PCT * 100,
            final.symbol,
        )
        return FillResult(None, REASON_ENTRY_DRIFT)
    setup = resolve_setup(intent, candles_4h, candles_1d, live_price, funding_rate)
    if setup is None:
        return FillResult(None, REASON_STALE_LEVELS)
    fresh_final = final.model_copy(
        update={
            "entry_price": setup.entry_price,
            "stop_price": setup.stop_price,
            "target_price": setup.target_price,
            "risk_reward": setup.risk_reward,
        }
    )
    return FillResult(fresh_final, REASON_SIGNAL_READY)


class ExecutionService:
    """Превращает одобренный сетап в рыночный филл по ЖИВОЙ цене на момент открытия.

    Сигнал рождается на снапшоте закрытия 4h-бара, но проходит медленный конвейер
    агентов/дебатов — к открытию snapshot-цена протухает. Сервис дотягивает свежие
    свечи и делегирует в evaluate_fill (drift-гейт + пере-резолв уровней от живой цены).
    """

    def __init__(self, ccxt: CcxtClient) -> None:
        self._ccxt = ccxt

    async def resolve_fill(self, candidate_signal: CandidateSignal) -> FillResult:
        intent = candidate_signal.setup_intent
        final = candidate_signal.final_signal
        if intent is None or final is None:
            return FillResult(None, REASON_STALE_LEVELS)
        symbol = candidate_signal.candidate.symbol
        funding_rate = candidate_signal.candidate.screener.signals.funding_rate
        try:
            candles_4h = await self._ccxt.fetch_ohlcv(
                symbol, timeframe="4h", limit=settings.SCREENER_4H_LIMIT
            )
            candles_1d = await self._ccxt.fetch_ohlcv(
                symbol, timeframe="1d", limit=settings.SCREENER_1D_LIMIT
            )
        except ccxt.BaseError:
            logger.warning(
                "fill: live price fetch failed for %s", symbol, exc_info=True
            )
            return FillResult(None, REASON_FILL_UNAVAILABLE)
        return evaluate_fill(intent, final, funding_rate, candles_4h, candles_1d)
