import logging
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

import ccxt.async_support as ccxt
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.engines.api.liquidation_hub import LiquidationHub
from app.engines.api.routers import equity, liquidations, market, research, signals
from app.adapters.clients.ccxt.client import CcxtClient
from core.settings import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Поднимает общий CCXT-клиент (один exchange на всё приложение) и hub ликвидаций.

    CcxtClient грузит markets один раз на старте; недоступность биржи нефатальна —
    app.state.ccxt=None, market-эндпоинты отдадут 503, остальное API живёт.
    LiquidationHub поднимает фоновые ws-стримы бирж. На shutdown — стоп hub и
    закрытие exchange.
    """
    async with AsyncExitStack() as stack:
        try:
            ccxt_client: CcxtClient | None = await stack.enter_async_context(
                CcxtClient()
            )
        except ccxt.BaseError:
            logger.warning("CCXT unavailable at startup, market endpoints disabled")
            ccxt_client = None
        app.state.ccxt = ccxt_client
        hub = LiquidationHub()
        await hub.start()
        app.state.liquidation_hub = hub
        logger.info("API ready")
        try:
            yield
        finally:
            await hub.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="TradingAgents Analytics API", lifespan=_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.API_CORS_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(market.router)
    app.include_router(signals.router)
    app.include_router(equity.router)
    app.include_router(liquidations.router)
    app.include_router(research.router)
    return app


app = create_app()


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
