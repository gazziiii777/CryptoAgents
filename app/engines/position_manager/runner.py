import asyncio
import logging

from app.adapters.clients.ccxt.client import CcxtClient
from app.services.positions.account_service import ensure_default_account
from app.services.positions.dispatch import dispatch_cycle
from app.services.positions.watcher import PositionWatcher
from app.services.screener.universe import get_liquid_perp_pairs
from core.settings import settings
from db.engine import session_scope

logger = logging.getLogger(__name__)


async def run_position_manager() -> None:
    """Always-on движок управления открытыми позициями: каждые POSITION_MANAGER_INTERVAL_S.

    Единственный писатель выходов: реконструирует управляемый стоп по 15m-свечам с момента
    входа и исполняет выход (стоп/тейк/безубыток/трейлинг/экспирация/funding/делистинг) +
    обновляет equity + персистит стадию стопа (алерт на переход). Сбой цикла не роняет
    движок; на старте позиции реконсилятся от входа (пропущенные за простой выходы ловятся).
    """
    while True:
        try:
            await _cycle()
        except Exception:
            logger.error("position-manager: cycle failed", exc_info=True)
        await asyncio.sleep(settings.POSITION_MANAGER_INTERVAL_S)


async def run_position_manager_once() -> int:
    """Один цикл управления позициями (для CLI/диагностики). Возвращает число закрытых."""
    return await _cycle()


async def _cycle() -> int:
    """Один цикл: закрытия/стадии стопа в БД (коммит), затем побочки (Telegram/research)."""
    universe = set(await get_liquid_perp_pairs())
    async with session_scope() as session, CcxtClient() as ccxt:
        account = await ensure_default_account(session)
        cycle = await PositionWatcher(session, ccxt, universe).run(account)
    await dispatch_cycle(cycle)
    logger.info("position-manager: cycle complete, closed=%d", len(cycle.closed_trades))
    return len(cycle.closed_trades)
