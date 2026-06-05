import asyncio
import logging
from decimal import Decimal
from typing import cast

from app.clients.ccxt.client import CcxtClient
from app.notifications.positions import notify_stop_update
from app.portfolio.account_service import ensure_default_account
from app.portfolio.exits import current_managed_stop
from core.settings import settings
from db.engine import session_scope
from db.models import ExitReason, VirtualPosition
from db.repositories.virtual_position_repo import VirtualPositionRepo

logger = logging.getLogger(__name__)


async def run_monitor() -> None:
    """Always-on монитор открытых позиций: раз в MONITOR_INTERVAL шлёт алерт при сдвиге стопа.

    Notify-only: НЕ закрывает позиции (авторитетный close — за 4h-watcher по 15m-реконструкции).
    Даёт near-real-time видимость по 5m-ценам: переход стопа в безубыток / активацию трейлинга.
    Состояние стопа на позицию помнит в памяти, чтобы слать алерт только на смену, не каждый цикл.
    """
    last_reason: dict[int, ExitReason] = {}
    while True:
        try:
            await _scan(last_reason)
        except Exception:
            logger.error("monitor: cycle failed", exc_info=True)
        await asyncio.sleep(settings.MONITOR_INTERVAL_S)


async def _scan(last_reason: dict[int, ExitReason]) -> None:
    async with session_scope() as session, CcxtClient() as ccxt:
        account = await ensure_default_account(session)
        positions = await VirtualPositionRepo(session).list_open(cast(int, account.id))
        open_ids: set[int] = set()
        for position in positions:
            position_id = cast(int, position.id)
            open_ids.add(position_id)
            await _scan_position(position_id, position, ccxt, last_reason)
        for closed_id in [pid for pid in last_reason if pid not in open_ids]:
            del last_reason[closed_id]


async def _scan_position(
    position_id: int,
    position: VirtualPosition,
    ccxt: CcxtClient,
    last_reason: dict[int, ExitReason],
) -> None:
    candles = await ccxt.fetch_ohlcv(
        position.symbol,
        timeframe=settings.MONITOR_TIMEFRAME,
        limit=settings.MONITOR_CANDLE_LIMIT,
    )
    stop, reason = current_managed_stop(
        position.side,
        position.entry_price,
        position.stop_price,
        candles,
        position.entry_ts,
        settings.BREAKEVEN_TRIGGER_R,
        settings.TRAIL_ACTIVATION_R,
        settings.TRAIL_DISTANCE_R,
    )
    if reason == last_reason.get(position_id):
        return
    last_reason[position_id] = reason
    if reason == ExitReason.STOP:
        return
    mark = Decimal(str(candles[-1].close)) if candles else position.entry_price
    logger.info(
        "monitor: %s stop moved to %s (stop=%s mark=%s)",
        position.symbol,
        reason.value,
        stop,
        mark,
    )
    await notify_stop_update(position, reason, stop, mark)
