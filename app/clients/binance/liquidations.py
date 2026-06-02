import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

from binance import AsyncClient, BinanceSocketManager
from binance.enums import FuturesType
from pydantic import ValidationError

from app.clients.binance.models import ForcedLiquidation
from core.settings import settings

logger = logging.getLogger(__name__)

_ALL_FORCE_ORDER_STREAM = "!forceOrder@arr"


async def stream_liquidations() -> AsyncIterator[ForcedLiquidation]:
    """Бесконечный стрим ликвидаций Binance USD-M с авто-реконнектом.

    Держит ws !forceOrder@arr; при обрыве логирует, ждёт RECONNECT_DELAY и
    переподключается заново (новый AsyncClient на каждое подключение). Битое
    отдельное сообщение пропускается, поток не падает.
    """
    while True:
        client = await AsyncClient.create()
        socket_manager = BinanceSocketManager(client)
        socket = socket_manager.futures_multiplex_socket(
            [_ALL_FORCE_ORDER_STREAM], futures_type=FuturesType.USD_M
        )
        try:
            async with socket as stream:
                logger.info("liquidation stream connected")
                while True:
                    message = await stream.recv()
                    event = _parse(message)
                    if event is not None:
                        yield event
        except Exception:
            logger.warning("liquidation stream dropped, reconnecting", exc_info=True)
        finally:
            await client.close_connection()
        await asyncio.sleep(settings.LIQUIDATION_RECONNECT_DELAY_S)


def _parse(message: dict[str, Any]) -> ForcedLiquidation | None:
    data = message.get("data")
    if not isinstance(data, dict):
        return None
    order = data.get("o")
    if not isinstance(order, dict):
        return None
    try:
        return ForcedLiquidation.model_validate(order)
    except ValidationError:
        logger.warning("failed to parse forced liquidation: %s", order)
        return None
