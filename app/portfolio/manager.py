import logging
from datetime import datetime
from decimal import Decimal
from typing import cast

from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.setup import FinalSignal
from app.notifications.positions import notify_position_opened
from app.portfolio.account_service import build_portfolio_state
from app.portfolio.leverage import compute_leverage
from app.portfolio.models import PortfolioState
from app.portfolio.sizing import compute_qty_by_margin, confidence_risk_pct
from core.constants.entities import ENTITY_POSITION
from core.settings import settings
from db.models import Account, Decision, EventType, PositionSide, VirtualPosition
from db.repositories.event_repo import EventRepo
from db.repositories.virtual_position_repo import VirtualPositionRepo

logger = logging.getLogger(__name__)

_DIRECTION_TO_SIDE = {"long": PositionSide.LONG, "short": PositionSide.SHORT}


class PortfolioManager:
    """4 pre-trade проверки + маржинальный сайзинг + открытие VirtualPosition.

    Полностью детерминированный (Python для всех правил риска). Порядок проверок:
    drawdown breaker → slot/направление → symbol dedup → funding kill-switch.
    Сайзинг маржинальный: margin_pct интерполируется по analyst_confluence, плечо —
    по setup_type/leverage_intent (см. compute_qty_by_margin / confidence_risk_pct).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._positions = VirtualPositionRepo(session)
        self._events = EventRepo(session)

    async def evaluate(
        self,
        *,
        account: Account,
        signal_id: int,
        final_signal: FinalSignal,
        funding_rate: float,
        bar_close_ts: datetime,
    ) -> Decision:
        """Прогоняет проверки; при TAKEN открывает позицию. Возвращает Decision."""
        state = await build_portfolio_state(self._session, account)
        side = _DIRECTION_TO_SIDE[final_signal.direction]

        gate = self._gate(state, side, funding_rate)
        if gate is not None:
            return gate
        if await self._positions.get_open_by_symbol(
            cast(int, account.id), final_signal.symbol
        ):
            return Decision.SKIPPED_DEDUP

        await self._open_position(account, signal_id, final_signal, side, bar_close_ts)
        return Decision.TAKEN

    def _gate(
        self, state: PortfolioState, side: PositionSide, funding_rate: float
    ) -> Decision | None:
        """Проверки, не требующие БД. None = прошли."""
        if state.drawdown_pct >= Decimal(str(settings.DRAWDOWN_HALT_PCT)):
            return Decision.SKIPPED_DRAWDOWN
        if state.open_count >= settings.MAX_CONCURRENT_POSITIONS:
            return Decision.SKIPPED_SLOT
        same_direction = (
            state.long_count if side == PositionSide.LONG else state.short_count
        )
        if same_direction >= settings.MAX_SAME_DIRECTION:
            return Decision.SKIPPED_SLOT
        if abs(funding_rate) >= settings.FUNDING_KILL_SWITCH_PCT:
            return Decision.SKIPPED_FUNDING
        return None

    async def _open_position(
        self,
        account: Account,
        signal_id: int,
        final_signal: FinalSignal,
        side: PositionSide,
        bar_close_ts: datetime,
    ) -> None:
        entry = Decimal(str(final_signal.entry_price))
        stop = Decimal(str(final_signal.stop_price))
        target = Decimal(str(final_signal.target_price))
        leverage = compute_leverage(
            final_signal.setup_type, final_signal.leverage_intent, settings.MAX_LEVERAGE
        )
        margin_pct = confidence_risk_pct(
            final_signal.analyst_confluence,
            settings.CONFLUENCE_GATE,
            Decimal(str(settings.MARGIN_PER_TRADE_MIN_PCT)),
            Decimal(str(settings.MARGIN_PER_TRADE_MAX_PCT)),
        )
        qty = compute_qty_by_margin(account.equity, entry, leverage, margin_pct)
        notional = entry * qty
        margin = notional / Decimal(leverage)
        position = await self._positions.create(
            VirtualPosition(
                account_id=cast(int, account.id),
                symbol=final_signal.symbol,
                side=side,
                entry_signal_id=signal_id,
                entry_ts=bar_close_ts,
                entry_price=entry,
                qty=qty,
                notional=notional,
                leverage=leverage,
                margin=margin,
                stop_price=stop,
                target_price=target,
            )
        )
        await self._events.append(
            event_type=EventType.POSITION_OPENED,
            entity_type=ENTITY_POSITION,
            entity_id=position.id,
            payload={
                "symbol": position.symbol,
                "side": side.value,
                "entry_price": str(entry),
                "stop_price": str(stop),
                "target_price": str(target),
                "qty": str(qty),
                "notional": str(notional),
                "leverage": leverage,
                "margin": str(margin),
                "leverage_intent": final_signal.leverage_intent,
                "margin_pct": str(margin_pct),
                "confluence_score": final_signal.confluence_score,
            },
        )
        logger.info(
            "position opened",
            extra={
                "symbol": position.symbol,
                "side": side.value,
                "qty": str(qty),
                "entry_price": str(entry),
                "notional": str(notional),
                "margin_pct": str(margin_pct),
            },
        )
        await notify_position_opened(
            position, final_signal.confluence_score, account.equity
        )
