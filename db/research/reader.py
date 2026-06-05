import logging

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.research.models import SignalRecord, TradeOutcome
from db.research.models.regime_performance import RegimePerformance

logger = logging.getLogger(__name__)


async def regime_performance(session: AsyncSession) -> list[RegimePerformance]:
    """Агрегирует закрытые сделки (TradeOutcome) по рыночному режиму (SignalRecord.macro_regime).

    Считает win-rate, средний и суммарный R, средний MFE и время удержания на каждый
    режим — основа для решения, нужен ли отдельный range-плейбук. Сделки без
    привязанного signal_record (режим неизвестен) в выборку не попадают (inner join).
    """
    stmt = (
        select(
            SignalRecord.macro_regime.label("regime"),
            func.count().label("trades"),
            func.sum(case((TradeOutcome.r_multiple > 0, 1), else_=0)).label("wins"),
            func.avg(TradeOutcome.r_multiple).label("avg_r"),
            func.sum(TradeOutcome.r_multiple).label("total_r"),
            func.avg(TradeOutcome.max_favorable_excursion_r).label("avg_mfe_r"),
            func.avg(TradeOutcome.holding_hours).label("avg_holding_hours"),
        )
        .select_from(TradeOutcome)
        .join(SignalRecord, TradeOutcome.signal_record_id == SignalRecord.id)
        .group_by(SignalRecord.macro_regime)
        .order_by(SignalRecord.macro_regime)
    )
    rows = (await session.execute(stmt)).all()
    return [
        RegimePerformance(
            regime=row.regime,
            trades=row.trades,
            win_rate=float(row.wins) / row.trades,
            avg_r=float(row.avg_r),
            total_r=float(row.total_r),
            avg_mfe_r=float(row.avg_mfe_r) if row.avg_mfe_r is not None else None,
            avg_holding_hours=float(row.avg_holding_hours),
        )
        for row in rows
    ]
