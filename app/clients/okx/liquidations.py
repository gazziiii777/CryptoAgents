import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from websockets.asyncio.client import ClientConnection, connect

from app.models.liquidations import NormalizedLiquidation
from core.settings import settings

logger = logging.getLogger(__name__)

_OKX_PUBLIC_WS_URL = "wss://ws.okx.com:8443/ws/v5/public"
_SUBSCRIBE_LIQUIDATIONS = json.dumps({
    "op": "subscribe",
    "args": [{"channel": "liquidation-orders", "instType": "SWAP"}],
})
_IDLE_PING_TIMEOUT_S = 20.0


async def stream_liquidations() -> AsyncIterator[NormalizedLiquidation]:
    """Бесконечный стрим ликвидаций OKX SWAP (all-market) с авто-реконнектом.

    Канал liquidation-orders instType=SWAP отдаёт все ликвидации одной подпиской.
    При обрыве логирует, ждёт RECONNECT_DELAY и переподключается заново.
    """
    while True:
        try:
            async with connect(_OKX_PUBLIC_WS_URL) as ws:
                await ws.send(_SUBSCRIBE_LIQUIDATIONS)
                logger.info("okx liquidation stream connected")
                async for event in _read(ws):
                    yield event
        except Exception:
            logger.warning(
                "okx liquidation stream dropped, reconnecting", exc_info=True
            )
        await asyncio.sleep(settings.LIQUIDATION_RECONNECT_DELAY_S)


async def _read(ws: ClientConnection) -> AsyncIterator[NormalizedLiquidation]:
    """Читает сообщения, шлёт app-level 'ping' на простое (OKX рвёт после 30с тишины)."""
    while True:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=_IDLE_PING_TIMEOUT_S)
        except TimeoutError:
            await ws.send("ping")
            continue
        for event in _parse(raw):
            yield event


def _parse(raw: str | bytes) -> list[NormalizedLiquidation]:
    if raw == "pong":
        return []
    try:
        message = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return []
    rows = message.get("data")
    if not isinstance(rows, list):
        return []
    events: list[NormalizedLiquidation] = []
    for row in rows:
        inst_id = row.get("instId")
        for detail in row.get("details", []):
            event = _parse_detail(inst_id, detail)
            if event is not None:
                events.append(event)
    return events


def _parse_detail(inst_id: str, detail: dict[str, Any]) -> NormalizedLiquidation | None:
    try:
        return NormalizedLiquidation(
            exchange="okx",
            symbol=inst_id,
            order_side=detail["side"],
            liquidated_side=detail["posSide"],
            price=float(detail["bkPx"]),
            quantity=float(detail["sz"]),
            trade_time_ms=int(detail["ts"]),
        )
    except (KeyError, ValueError, TypeError):
        return None
