import logging

from app.adapters.notifications.positions import notify_position_closed, notify_stop_update
from app.domain.risk.models import ClosedTrade, CycleOutcome
from db.research.writer import record_trade_outcome

logger = logging.getLogger(__name__)


async def dispatch_closed_trade(trade: ClosedTrade) -> None:
    """Побочки закрытия, выполняемые ПОСЛЕ коммита: Telegram-карточка + запись исхода в research.

    Вынесены из транзакции закрытия: операционная правда (позиция + событие + баланс)
    коммитится атомарно, а эти вторичные эффекты идут после — без дублей при откате цикла.
    """
    await notify_position_closed(trade.position, trade.new_balance)
    await record_trade_outcome(
        trade.position,
        exit_price=trade.exit_price,
        exit_ts=trade.exit_ts,
        exit_reason=trade.exit_reason.value,
        realized_pnl=trade.realized_pnl,
        fees=trade.fees,
        funding=trade.funding,
        mfe_r=trade.mfe_r,
    )


async def dispatch_cycle(cycle: CycleOutcome) -> None:
    """Рассылает побочки цикла ПОСЛЕ коммита; сбой по одной позиции не блокирует остальные."""
    for trade in cycle.closed_trades:
        try:
            await dispatch_closed_trade(trade)
        except Exception:
            logger.error(
                "dispatch: closed side-effect failed for %s",
                trade.position.symbol,
                exc_info=True,
            )
    for move in cycle.stop_moves:
        try:
            await notify_stop_update(move.position, move.reason, move.stop, move.mark)
        except Exception:
            logger.error(
                "dispatch: stop-move side-effect failed for %s",
                move.position.symbol,
                exc_info=True,
            )
