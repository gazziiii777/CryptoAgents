import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import ccxt.async_support as ccxt
from pydantic import ValidationError
from websockets.asyncio.client import ClientConnection, connect

from app.domain.models.liquidations import NormalizedLiquidation
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

    На каждом подключении тянет contractSize по инструментам (OKX отдаёт sz в
    контрактах, qty в базовой валюте = sz × contractSize). Встроенный keepalive
    websockets отключён (ping_interval=None) — OKX ждёт app-level 'ping', держим
    только его, чтобы не было ложных реконнектов от двух механизмов.
    """
    while True:
        try:
            contract_sizes = await _swap_contract_sizes()
            async with connect(_OKX_PUBLIC_WS_URL, ping_interval=None) as ws:
                await ws.send(_SUBSCRIBE_LIQUIDATIONS)
                logger.info("okx liquidation stream connected")
                async for event in _read(ws, contract_sizes):
                    yield event
        except Exception:
            logger.warning(
                "okx liquidation stream dropped, reconnecting", exc_info=True
            )
        await asyncio.sleep(settings.LIQUIDATION_RECONNECT_DELAY_S)


async def _swap_contract_sizes() -> dict[str, float]:
    """instId → contractSize только для LINEAR swap'ов (USDT/USDC-margined).

    Inverse (coin-margined, BTC-USD-SWAP) исключаются: у них contractSize в USD, и
    notional считается иначе; мы их не торгуем, как и Binance/Bybit-сборщики.
    """
    exchange = ccxt.okx({"options": {"defaultType": "swap"}})
    try:
        await exchange.load_markets()
        return {
            market["id"]: float(market["contractSize"])
            for market in exchange.markets.values()
            if market.get("swap")
            and market.get("linear")
            and market.get("contractSize")
        }
    finally:
        await exchange.close()


async def _read(
    ws: ClientConnection, contract_sizes: dict[str, float]
) -> AsyncIterator[NormalizedLiquidation]:
    """Читает сообщения, шлёт app-level 'ping' на простое (OKX рвёт после 30с тишины)."""
    while True:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=_IDLE_PING_TIMEOUT_S)
        except TimeoutError:
            await ws.send("ping")
            continue
        for event in _parse(raw, contract_sizes):
            yield event


def _parse(
    raw: str | bytes, contract_sizes: dict[str, float]
) -> list[NormalizedLiquidation]:
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
        if not isinstance(inst_id, str):
            continue
        contract_size = contract_sizes.get(inst_id)
        if contract_size is None:
            continue
        for detail in row.get("details", []):
            event = _parse_detail(inst_id, detail, contract_size)
            if event is not None:
                events.append(event)
    return events


def _parse_detail(
    inst_id: str, detail: dict[str, Any], contract_size: float
) -> NormalizedLiquidation | None:
    try:
        return NormalizedLiquidation(
            exchange="okx",
            symbol=inst_id,
            order_side=detail["side"],
            liquidated_side=detail["posSide"],
            price=float(detail["bkPx"]),
            quantity=float(detail["sz"]) * contract_size,
            trade_time_ms=int(detail["ts"]),
        )
    except (KeyError, ValueError, TypeError, ValidationError):
        return None
