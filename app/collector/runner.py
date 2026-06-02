import asyncio
import logging
import time

from app.clients.binance.liquidations import stream_liquidations
from app.clients.binance.models import ForcedLiquidation
from core.settings import settings
from db.research.writer import record_liquidations

logger = logging.getLogger(__name__)


async def run_collector() -> None:
    """Собирает поток ликвидаций Binance и пишет в research-БД батчами.

    Продьюсер держит ws-стрим и кладёт события в очередь; консьюмер флашит батч
    по достижении BATCH_SIZE либо по истечении FLUSH_INTERVAL с момента прошлого
    флаша (что раньше) — так буфер не копится в памяти при ровном потоке и пишется
    даже в тихие периоды. Очередь развязывает таймаут консьюмера от ws-соединения:
    флаш по таймеру не рвёт стрим.
    """
    queue: asyncio.Queue[ForcedLiquidation] = asyncio.Queue()
    producer = asyncio.create_task(_produce(queue))
    try:
        await _consume(queue)
    finally:
        producer.cancel()


async def _produce(queue: asyncio.Queue[ForcedLiquidation]) -> None:
    async for event in stream_liquidations():
        await queue.put(event)


async def _consume(queue: asyncio.Queue[ForcedLiquidation]) -> None:
    batch: list[ForcedLiquidation] = []
    last_flush = time.monotonic()
    while True:
        try:
            event = await asyncio.wait_for(
                queue.get(), timeout=settings.LIQUIDATION_FLUSH_INTERVAL_S
            )
        except TimeoutError:
            event = None
        if event is not None:
            batch.append(event)
        flush_due = (
            time.monotonic() - last_flush
        ) >= settings.LIQUIDATION_FLUSH_INTERVAL_S
        if batch and (len(batch) >= settings.LIQUIDATION_BATCH_SIZE or flush_due):
            await record_liquidations(batch)
            logger.info("liquidations: flushed %d events", len(batch))
            batch = []
            last_flush = time.monotonic()
