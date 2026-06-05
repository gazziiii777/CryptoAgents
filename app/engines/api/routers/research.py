from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.api.deps import get_research_session
from app.engines.api.models import RegimePerformanceOut
from db.research.reader import regime_performance

router = APIRouter(prefix="/api/research", tags=["research"])


@router.get("/regime-performance", response_model=list[RegimePerformanceOut])
async def get_regime_performance(
    session: AsyncSession = Depends(get_research_session),
) -> list[RegimePerformanceOut]:
    rows = await regime_performance(session)
    return [RegimePerformanceOut.from_domain(row) for row in rows]
