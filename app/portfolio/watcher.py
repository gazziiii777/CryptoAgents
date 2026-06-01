import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import cast

from sqlmodel.ext.asyncio.session import AsyncSession

from app.clients.ccxt.client import CcxtClient
from app.clients.ccxt.models import OHLCVCandle
from app.models.setup import CryptoSetup
from app.notifications.positions import notify_position_closed
from app.portfolio.exits import evaluate_candle_exit, funding_cycles, is_expired
from app.portfolio.models import ExitOutcome
from app.portfolio.pnl import (
    entry_exit_fees,
    funding_cost,
    realized_pnl,
    unrealized_pnl,
)
from core.constants.entities import ENTITY_POSITION
from core.constants.time import MS_PER_SECOND
from db.research.writer import record_trade_outcome
from core.settings import settings
from db._time import utcnow
from db.models import Account, EventType, ExitReason, PositionState, VirtualPosition
from db.repositories.account_repo import AccountRepo
from db.repositories.event_repo import EventRepo
from db.repositories.signal_repo import SignalRepo
from db.repositories.virtual_position_repo import VirtualPositionRepo

logger = logging.getLogger(__name__)

_FUNDING_HISTORY_LIMIT = 1


class PositionWatcher:
    """4h-тик по OPEN-позициям: stop/target/expiry/funding/delisting → закрытие + PnL.

    Каждый прогон реконсилит состояние из БД (recovery-safe): выходы проверяются по
    всем свечам с момента входа, поэтому пропущенные за простой stop/target ловятся.
    """

    def __init__(
        self, session: AsyncSession, ccxt: CcxtClient, universe_symbols: set[str]
    ) -> None:
        self._session = session
        self._ccxt = ccxt
        self._universe = universe_symbols
        self._positions = VirtualPositionRepo(session)
        self._accounts = AccountRepo(session)
        self._events = EventRepo(session)
        self._signals = SignalRepo(session)

    async def run(self, account: Account) -> int:
        """Реконсиляция + тик. Возвращает число закрытых позиций."""
        positions = await self._positions.list_open(cast(int, account.id))
        if positions:
            await self._events.append(
                event_type=EventType.RESTART_RECOVERY,
                payload={"open_position_ids": [position.id for position in positions]},
            )
        closed = 0
        open_marks: list[tuple[VirtualPosition, Decimal]] = []
        for position in positions:
            mark = await self._process(account, position)
            if position.state == PositionState.CLOSED:
                closed += 1
            elif mark is not None:
                open_marks.append((position, mark))
        await self._refresh_equity(account, open_marks)
        return closed

    async def force_close(
        self,
        account: Account,
        position: VirtualPosition,
        price: Decimal,
        reason: ExitReason,
    ) -> Decimal:
        """Принудительно закрывает позицию по цене price. Возвращает realized PnL."""
        funding_rate = await self._latest_funding(position.symbol)
        outcome = ExitOutcome(reason, price, utcnow())
        return await self._close(account, position, outcome, funding_rate)

    async def _process(
        self, account: Account, position: VirtualPosition
    ) -> Decimal | None:
        """Обрабатывает одну позицию. None — закрыта; иначе текущая mark-цена."""
        candles = await self._ccxt.fetch_ohlcv(
            position.symbol, timeframe="4h", limit=settings.SCREENER_4H_LIMIT
        )
        if not candles:
            logger.warning("no candles for open position %s", position.symbol)
            return None
        funding_rate = await self._latest_funding(position.symbol)
        last_price = Decimal(str(candles[-1].close))

        outcome = await self._find_exit(position, candles, funding_rate, last_price)
        if outcome is None:
            return last_price
        await self._close(account, position, outcome, funding_rate)
        return None

    async def _find_exit(
        self,
        position: VirtualPosition,
        candles: list[OHLCVCandle],
        funding_rate: float,
        last_price: Decimal,
    ) -> ExitOutcome | None:
        for candle in candles:
            candle_ts = datetime.fromtimestamp(
                candle.timestamp / MS_PER_SECOND, tz=timezone.utc
            )
            if candle_ts <= position.entry_ts:
                continue
            outcome = evaluate_candle_exit(
                position.side,
                position.stop_price,
                position.target_price,
                candle,
                candle_ts,
            )
            if outcome is not None:
                return outcome

        now = utcnow()
        if position.symbol not in self._universe:
            return ExitOutcome(ExitReason.DELISTED, last_price, now)
        if abs(funding_rate) >= settings.FUNDING_KILL_SWITCH_PCT:
            return ExitOutcome(ExitReason.EXTREME_FUNDING, last_price, now)
        valid_hours = await self._valid_hours(position.entry_signal_id)
        if valid_hours is not None and is_expired(position.entry_ts, valid_hours, now):
            return ExitOutcome(ExitReason.EXPIRED, last_price, now)
        return None

    async def _close(
        self,
        account: Account,
        position: VirtualPosition,
        outcome: ExitOutcome,
        funding_rate: float,
    ) -> Decimal:
        fee_rate = Decimal(str(settings.TAKER_FEE_RATE))
        rate = Decimal(str(funding_rate))
        cycles = funding_cycles(position.entry_ts, outcome.ts)
        pnl = realized_pnl(
            position.side,
            position.entry_price,
            outcome.price,
            position.qty,
            fee_rate,
            rate,
            cycles,
        )
        fees = entry_exit_fees(
            position.entry_price, outcome.price, position.qty, fee_rate
        )
        funding = funding_cost(
            position.side, position.entry_price, position.qty, rate, cycles
        )
        await self._positions.close(
            position,
            exit_ts=outcome.ts,
            exit_price=outcome.price,
            exit_reason=outcome.reason,
            realized_pnl=pnl,
            simulated_fees=fees,
            simulated_funding=funding,
        )
        account.current_balance += pnl
        await self._accounts.update_balances(
            account,
            current_balance=account.current_balance,
            equity=account.current_balance,
            update_peak=False,
        )
        await self._events.append(
            event_type=EventType.POSITION_CLOSED,
            entity_type=ENTITY_POSITION,
            entity_id=position.id,
            payload={
                "symbol": position.symbol,
                "exit_reason": outcome.reason.value,
                "exit_price": str(outcome.price),
                "realized_pnl": str(pnl),
            },
        )
        logger.info(
            "position closed",
            extra={
                "symbol": position.symbol,
                "exit_reason": outcome.reason.value,
                "realized_pnl": str(pnl),
            },
        )
        await record_trade_outcome(
            position,
            exit_price=outcome.price,
            exit_ts=outcome.ts,
            exit_reason=outcome.reason.value,
            realized_pnl=pnl,
            fees=fees,
            funding=funding,
        )
        await notify_position_closed(position, account.current_balance)
        return pnl

    async def _refresh_equity(
        self, account: Account, open_marks: list[tuple[VirtualPosition, Decimal]]
    ) -> None:
        unrealized = sum(
            (
                unrealized_pnl(position.side, position.entry_price, mark, position.qty)
                for position, mark in open_marks
            ),
            Decimal(0),
        )
        await self._accounts.update_balances(
            account,
            current_balance=account.current_balance,
            equity=account.current_balance + unrealized,
        )

    async def _latest_funding(self, symbol: str) -> float:
        history = await self._ccxt.fetch_funding_rate_history(
            symbol, limit=_FUNDING_HISTORY_LIMIT
        )
        if not history:
            return 0.0
        return history[-1].funding_rate

    async def _valid_hours(self, entry_signal_id: int) -> int | None:
        signal = await self._signals.get(entry_signal_id)
        if signal is None or signal.crypto_setup_json is None:
            return None
        return CryptoSetup.model_validate(signal.crypto_setup_json).valid_hours
