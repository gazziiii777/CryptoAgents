from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.engines.api.deps import get_ccxt, get_session
from app.engines.api.models import AccountOut, ClosedTradeOut, PositionOut
from app.adapters.clients.ccxt.client import CcxtClient
from core.settings import settings
from db.models import Account
from db.repositories.account_repo import AccountRepo
from db.repositories.virtual_position_repo import VirtualPositionRepo

router = APIRouter(prefix="/api", tags=["equity"])

_DEFAULT_TRADES_LIMIT = 50
_MAX_TRADES_LIMIT = 200


async def _require_account(session: AsyncSession) -> Account:
    account = await AccountRepo(session).get_by_name(settings.DEFAULT_ACCOUNT_NAME)
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="no paper account yet"
        )
    return account


async def _open_positions(
    session: AsyncSession, ccxt_client: CcxtClient, account: Account
) -> list[PositionOut]:
    """Открытые позиции аккаунта с live mark-ценой и нереализованным PnL.

    Берёт открытые позиции из БД, одним запросом тянет mark по их символам,
    маппит в DTO. Сбой фетча цен нефатален — позиции вернутся без mark/uPnL.
    """
    positions = await VirtualPositionRepo(session).list_open(cast(int, account.id))
    if not positions:
        return []
    symbols = list({position.symbol for position in positions})
    marks: dict[str, float] = {}
    try:
        marks = await ccxt_client.fetch_last_prices(symbols)
    except Exception:
        marks = {}
    return [
        PositionOut.from_domain(position, mark_price=marks.get(position.symbol))
        for position in positions
    ]


@router.get("/account", response_model=AccountOut)
async def get_account(
    session: AsyncSession = Depends(get_session),
    ccxt_client: CcxtClient = Depends(get_ccxt),
) -> AccountOut:
    """Снимок paper-аккаунта: equity/peak + число открытых позиций и суммарный uPnL."""
    account = await _require_account(session)
    positions = await _open_positions(session, ccxt_client, account)
    unrealized = sum(
        position.unrealized_pnl
        for position in positions
        if position.unrealized_pnl is not None
    )
    return AccountOut.from_domain(
        account, open_positions=len(positions), unrealized_pnl=float(unrealized)
    )


@router.get("/positions", response_model=list[PositionOut])
async def list_positions(
    session: AsyncSession = Depends(get_session),
    ccxt_client: CcxtClient = Depends(get_ccxt),
) -> list[PositionOut]:
    account = await _require_account(session)
    return await _open_positions(session, ccxt_client, account)


@router.get("/trades", response_model=list[ClosedTradeOut])
async def list_trades(
    limit: int = Query(default=_DEFAULT_TRADES_LIMIT, ge=1, le=_MAX_TRADES_LIMIT),
    session: AsyncSession = Depends(get_session),
) -> list[ClosedTradeOut]:
    account = await _require_account(session)
    closed = await VirtualPositionRepo(session).list_recent_closed(
        cast(int, account.id), limit=limit
    )
    return [ClosedTradeOut.from_domain(position) for position in closed]
