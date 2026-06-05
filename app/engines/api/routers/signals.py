from fastapi import APIRouter, Depends, Query
from sqlmodel.ext.asyncio.session import AsyncSession

from app.engines.api.deps import get_session
from app.engines.api.models import SignalOut
from db.repositories.signal_repo import SignalRepo

router = APIRouter(prefix="/api", tags=["signals"])

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 200


@router.get("/signals", response_model=list[SignalOut])
async def list_signals(
    limit: int = Query(default=_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    session: AsyncSession = Depends(get_session),
) -> list[SignalOut]:
    signals = await SignalRepo(session).list_recent(limit=limit)
    return [SignalOut.from_domain(signal) for signal in signals]
