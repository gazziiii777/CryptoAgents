from collections.abc import AsyncIterator

from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession as ResearchSession
from sqlmodel.ext.asyncio.session import AsyncSession

from app.engines.api.liquidation_hub import LiquidationHub
from app.adapters.clients.ccxt.client import CcxtClient
from db.engine import session_scope
from db.research.engine import research_session_scope


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_scope() as session:
        yield session


async def get_research_session() -> AsyncIterator[ResearchSession]:
    async with research_session_scope() as session:
        yield session


def get_ccxt(request: Request) -> CcxtClient:
    client = request.app.state.ccxt
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="exchange data unavailable",
        )
    return client


def get_liquidation_hub(request: Request) -> LiquidationHub:
    return request.app.state.liquidation_hub
