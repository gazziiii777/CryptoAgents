import asyncio
import logging
from collections.abc import AsyncIterator

from app.adapters.clients.binance.liquidations import stream_liquidations as binance_stream
from app.adapters.clients.bybit.liquidations import stream_liquidations as bybit_stream
from app.adapters.clients.okx.liquidations import stream_liquidations as okx_stream
from app.domain.models.liquidations import NormalizedLiquidation

logger = logging.getLogger(__name__)

_SUBSCRIBER_QUEUE_MAXSIZE = 500


class LiquidationHub:
    """Fan-out живых ликвидаций со всех бирж на подписчиков-вебсокеты.

    На старте поднимает по одной фоновой задаче на биржу (Binance/OKX/Bybit),
    каждая бесконечно тянет свой ws-стрим и раздаёт события в очереди всех
    подключённых клиентов. Медленный клиент с переполненной очередью теряет
    события (а не тормозит остальных). stop() отменяет задачи на shutdown.
    """

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[NormalizedLiquidation]] = set()
        self._tasks: list[asyncio.Task[None]] = []

    async def start(self) -> None:
        self._tasks = [
            asyncio.create_task(self._pump(binance_stream(), "binance")),
            asyncio.create_task(self._pump(okx_stream(), "okx")),
            asyncio.create_task(self._pump(bybit_stream(), "bybit")),
        ]

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

    def subscribe(self) -> asyncio.Queue[NormalizedLiquidation]:
        queue: asyncio.Queue[NormalizedLiquidation] = asyncio.Queue(
            maxsize=_SUBSCRIBER_QUEUE_MAXSIZE
        )
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[NormalizedLiquidation]) -> None:
        self._subscribers.discard(queue)

    async def _pump(
        self, stream: AsyncIterator[NormalizedLiquidation], exchange: str
    ) -> None:
        try:
            async for event in stream:
                self._broadcast(event)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("liquidation pump for %s crashed", exchange)

    def _broadcast(self, event: NormalizedLiquidation) -> None:
        for queue in self._subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.debug("dropping liquidation for slow subscriber")
