import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.engines.api.models import LiquidationOut

logger = logging.getLogger(__name__)

router = APIRouter(tags=["liquidations"])


@router.websocket("/ws/liquidations")
async def ws_liquidations(websocket: WebSocket) -> None:
    """Стримит живые ликвидации клиенту: подписка на hub → пуш каждого события.

    Подписывается в общий LiquidationHub, ретранслирует события в сокет, на
    дисконнекте снимает подписку. Каждый клиент — своя очередь.
    """
    hub = websocket.app.state.liquidation_hub
    await websocket.accept()
    queue = hub.subscribe()
    try:
        while True:
            event = await queue.get()
            await websocket.send_json(
                LiquidationOut.from_domain(event).model_dump(by_alias=True)
            )
    except WebSocketDisconnect:
        logger.info("liquidations ws client disconnected")
    finally:
        hub.unsubscribe(queue)
