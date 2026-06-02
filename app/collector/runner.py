import asyncio
import logging
import time
from collections.abc import AsyncIterator

from app.clients.binance.liquidations import stream_liquidations as stream_binance
from app.clients.bybit.liquidations import stream_liquidations as stream_bybit
from app.clients.okx.liquidations import stream_liquidations as stream_okx
from app.models.liquidations import NormalizedLiquidation
from core.settings import settings
from db.research.writer import record_liquidations

logger = logging.getLogger(__name__)


async def run_collector() -> None:
    """Собирает потоки ликвидаций Binance + OKX + Bybit и пишет в research-БД батчами.

    По продьюсеру на биржу кладут события в общую очередь; консьюмер флашит батч
    по достижении BATCH_SIZE либо по истечении FLUSH_INTERVAL с момента прошлого
    флаша (что раньше) — так буфер не копится в памяти при ровном потоке и пишется
    даже в тихие периоды. Очередь развязывает таймаут консьюмера от ws-соединений:
    флаш по таймеру не рвёт стримы, падение одной биржи не трогает другие.
    """
    queue: asyncio.Queue[NormalizedLiquidation] = asyncio.Queue()
    producers = [
        asyncio.create_task(_drain(stream_binance(), queue)),
        asyncio.create_task(_drain(stream_okx(), queue)),
        asyncio.create_task(_drain(stream_bybit(), queue)),
    ]
    try:
        await _consume(queue)
    finally:
        for producer in producers:
            producer.cancel()


async def _drain(
    stream: AsyncIterator[NormalizedLiquidation],
    queue: asyncio.Queue[NormalizedLiquidation],
) -> None:
    async for event in stream:
        await queue.put(event)


async def _consume(queue: asyncio.Queue[NormalizedLiquidation]) -> None:
    batch: list[NormalizedLiquidation] = []
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
