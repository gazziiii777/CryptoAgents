import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

import ccxt.async_support as ccxt
from websockets.asyncio.client import ClientConnection, connect

from app.models.liquidations import NormalizedLiquidation
from core.settings import settings

logger = logging.getLogger(__name__)

_BYBIT_LINEAR_WS_URL = "wss://stream.bybit.com/v5/public/linear"
_SUBSCRIBE_BATCH = 10
_IDLE_PING_TIMEOUT_S = 15.0
_PING = json.dumps({"op": "ping"})


async def stream_liquidations() -> AsyncIterator[NormalizedLiquidation]:
    """Бесконечный стрим ликвидаций Bybit linear (all-market) с авто-реконнектом.

    У Bybit нет общего потока — на каждом подключении тянем список linear
    USDT-перпов через ccxt и подписываемся на allLiquidation.{symbol} по всем
    (батчами по 10 — лимит Bybit). Соединение пересоздаётся раз в RESUB_INTERVAL,
    чтобы подхватить новые листинги (список символов берётся заново). На простое
    шлём {op:ping}. Битое сообщение пропускается, поток не падает.
    """
    while True:
        try:
            symbols = await _linear_perp_ids()
            deadline = time.monotonic() + settings.LIQUIDATION_BYBIT_RESUB_INTERVAL_S
            async with connect(_BYBIT_LINEAR_WS_URL, max_size=None) as ws:
                await _subscribe_all(ws, symbols)
                logger.info(
                    "bybit liquidation stream connected (%d symbols)", len(symbols)
                )
                async for event in _read(ws, deadline):
                    yield event
        except Exception:
            logger.warning(
                "bybit liquidation stream dropped, reconnecting", exc_info=True
            )
        await asyncio.sleep(settings.LIQUIDATION_RECONNECT_DELAY_S)


async def _linear_perp_ids() -> list[str]:
    exchange = ccxt.bybit({"options": {"defaultType": "swap"}})
    try:
        await exchange.load_markets()
        return [
            market["id"]
            for market in exchange.markets.values()
            if market.get("swap")
            and market.get("linear")
            and market.get("quote") == settings.QUOTE_CURRENCY
            and market.get("active")
        ]
    finally:
        await exchange.close()


async def _subscribe_all(ws: ClientConnection, symbols: list[str]) -> None:
    for start in range(0, len(symbols), _SUBSCRIBE_BATCH):
        topics = [
            f"allLiquidation.{symbol}"
            for symbol in symbols[start : start + _SUBSCRIBE_BATCH]
        ]
        await ws.send(json.dumps({"op": "subscribe", "args": topics}))


async def _read(
    ws: ClientConnection, deadline: float
) -> AsyncIterator[NormalizedLiquidation]:
    """Читает сообщения до deadline, шлёт {op:ping} на простое (Bybit ждёт ping ~20с).

    По достижении deadline выходит — внешний цикл переподключается и заново тянет
    список символов, подхватывая новые листинги.
    """
    while time.monotonic() < deadline:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=_IDLE_PING_TIMEOUT_S)
        except TimeoutError:
            await ws.send(_PING)
            continue
        for event in _parse(raw):
            yield event


def _parse(raw: str | bytes) -> list[NormalizedLiquidation]:
    try:
        message = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return []
    if not str(message.get("topic", "")).startswith("allLiquidation"):
        return []
    events: list[NormalizedLiquidation] = []
    for row in message.get("data", []):
        event = _parse_row(row)
        if event is not None:
            events.append(event)
    return events


def _parse_row(row: dict[str, Any]) -> NormalizedLiquidation | None:
    try:
        position_side = row["S"]
        return NormalizedLiquidation(
            exchange="bybit",
            symbol=row["s"],
            order_side=position_side,
            liquidated_side="long" if position_side == "Buy" else "short",
            price=float(row["p"]),
            quantity=float(row["v"]),
            trade_time_ms=int(row["T"]),
        )
    except (KeyError, ValueError, TypeError):
        return None
