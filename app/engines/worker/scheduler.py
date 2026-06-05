import asyncio
import logging
import math
import signal
from datetime import UTC, datetime

from app.engines.worker.pipeline.runner import run_pipeline
from core.constants.time import MINUTES_PER_HOUR, SECONDS_PER_MINUTE
from db.engine import dispose_engine
from db.research.engine import dispose_research_engine

logger = logging.getLogger(__name__)

_TICK_HOURS = 4
_TICK_LAG_SECONDS = 60
_CYCLE_SECONDS = _TICK_HOURS * MINUTES_PER_HOUR * SECONDS_PER_MINUTE


def seconds_until_next_tick(now: datetime) -> float:
    """Секунды до следующего закрытия 4h-бара (00/04/08/.../UTC) + лаг на готовность данных."""
    epoch = now.timestamp()
    next_boundary = (math.floor(epoch / _CYCLE_SECONDS) + 1) * _CYCLE_SECONDS
    return (next_boundary - epoch) + _TICK_LAG_SECONDS


async def run_tick(symbol_limit: int | None = None) -> None:
    """Тик worker'а: только pipeline (скрин → агенты → открытие по живой цене).

    Выходы и управление открытыми позициями — за position-manager'ом (always-on, 5 мин),
    единственным писателем выходов. Worker позиции только открывает.
    """
    await run_pipeline(symbol_limit)


async def run_once(symbol_limit: int | None = None) -> None:
    """Один тик с гарантированным dispose engine'ов (для --once / one-off запуска).

    run_forever диспоузит в своём finally; разовый запуск идёт мимо него, поэтому
    оборачиваем здесь — иначе пул aiomysql собирается GC после закрытия loop
    ('Event loop is closed' на выходе).
    """
    try:
        await run_tick(symbol_limit)
    finally:
        await dispose_engine()
        await dispose_research_engine()


def _install_stop_handlers(stop: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stop.set))


async def run_forever(symbol_limit: int | None = None) -> None:
    """Бесконечный цикл: на старте сразу прогон pipeline, затем сон до следующего 4h-бара.

    Первый прогон идёт немедленно при запуске, дальше — по закрытию каждого 4h-бара.
    Выходы/реконсиляция позиций — за position-manager'ом. Сбой тика логируется и не роняет
    цикл. SIGTERM/SIGINT — мягкая остановка.
    """
    stop = asyncio.Event()
    _install_stop_handlers(stop)
    logger.info("scheduler started (4h tick, first run immediate)")

    try:
        while not stop.is_set():
            try:
                await run_tick(symbol_limit)
            except Exception:
                logger.error("scheduler: tick failed", exc_info=True)
            delay = seconds_until_next_tick(datetime.now(UTC))
            logger.info(
                "scheduler: sleeping until next tick", extra={"delay_s": round(delay)}
            )
            try:
                await asyncio.wait_for(stop.wait(), timeout=delay)
                break
            except TimeoutError:
                pass
    finally:
        await dispose_engine()
        await dispose_research_engine()
        logger.info("scheduler stopped")
