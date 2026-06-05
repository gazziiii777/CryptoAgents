import logging
from decimal import Decimal
from typing import cast

from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.clients.ccxt.client import CcxtClient
from app.adapters.clients.ccxt.models import OHLCVCandle
from app.domain.models.setup import CryptoSetup
from app.domain.risk.exits import (
    current_managed_stop,
    funding_cycles,
    is_expired,
    walk_managed_exit,
)
from app.domain.risk.models import (
    ClosedTrade,
    CycleOutcome,
    ExitOutcome,
    ProcessResult,
    StopMove,
)
from app.domain.risk.pnl import (
    entry_exit_fees,
    funding_cost,
    realized_pnl,
    unrealized_pnl,
)
from core.constants.entities import ENTITY_POSITION
from core.settings import settings
from db._time import utcnow
from db.models import Account, EventType, ExitReason, StopStage, VirtualPosition
from db.repositories.account_repo import AccountRepo
from db.repositories.event_repo import EventRepo
from db.repositories.signal_repo import SignalRepo
from db.repositories.virtual_position_repo import VirtualPositionRepo

logger = logging.getLogger(__name__)

_FUNDING_HISTORY_LIMIT = 1
_STAGE_BY_REASON: dict[ExitReason, StopStage] = {
    ExitReason.STOP: StopStage.INITIAL,
    ExitReason.BREAKEVEN: StopStage.BREAKEVEN,
    ExitReason.TRAILING_STOP: StopStage.TRAILING,
}


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

    async def run(self, account: Account) -> CycleOutcome:
        """Реконсиляция + тик. Возвращает CycleOutcome (закрытия + сдвиги стопа для побочек).

        Каждая позиция обрабатывается в своём SAVEPOINT: сбой по одной изолирован — её
        частичные записи откатываются, остальные продолжают. Побочки (Telegram/research) сюда
        НЕ входят — их диспатчит вызывающий ПОСЛЕ коммита, чтобы откат не плодил дубли.
        """
        positions = await self._positions.list_open(cast(int, account.id))
        if positions:
            await self._events.append(
                event_type=EventType.RESTART_RECOVERY,
                payload={"open_position_ids": [position.id for position in positions]},
            )
        cycle = CycleOutcome()
        open_marks: list[tuple[VirtualPosition, Decimal]] = []
        for position in positions:
            try:
                async with self._session.begin_nested():
                    result = await self._process(account, position)
            except Exception:
                logger.error(
                    "position-manager: process failed for %s",
                    position.symbol,
                    exc_info=True,
                )
                continue
            if result.closed is not None:
                cycle.closed_trades.append(result.closed)
                continue
            if result.stop_move is not None:
                cycle.stop_moves.append(result.stop_move)
            if result.mark is not None:
                open_marks.append((position, result.mark))
        await self._refresh_equity(account, open_marks)
        return cycle

    async def force_close(
        self,
        account: Account,
        position: VirtualPosition,
        price: Decimal,
        reason: ExitReason,
    ) -> ClosedTrade:
        """Принудительно закрывает позицию по цене price. Побочки диспатчит вызывающий после коммита."""
        funding_rate = await self._latest_funding(position.symbol)
        outcome = ExitOutcome(reason, price, utcnow())
        return await self._close(account, position, outcome, funding_rate, mfe_r=0.0)

    async def _process(
        self, account: Account, position: VirtualPosition
    ) -> ProcessResult:
        """Обрабатывает одну позицию: закрытие ИЛИ обновление стадии стопа + текущая mark-цена.

        Выходы считаются по мелкому таймфрейму (EXIT_TIMEFRAME, по умолч. 15m) — это даёт
        внутрибарную точность стоп/тейк/трейлинга, которой нет на 4h OHLC. Все записи в БД здесь;
        побочки (Telegram/research) не шлёт — возвращает их в ProcessResult для диспатча после коммита.
        """
        candles = await self._ccxt.fetch_ohlcv(
            position.symbol,
            timeframe=settings.EXIT_TIMEFRAME,
            limit=settings.EXIT_CANDLE_LIMIT,
        )
        if not candles:
            logger.warning("no candles for open position %s", position.symbol)
            return ProcessResult()
        funding_rate = await self._latest_funding(position.symbol)
        last_price = Decimal(str(candles[-1].close))

        outcome, mfe_r = await self._find_exit(
            position, candles, funding_rate, last_price
        )
        if outcome is None:
            stop_move = await self._update_stop_stage(position, candles, last_price)
            return ProcessResult(stop_move=stop_move, mark=last_price)
        closed = await self._close(account, position, outcome, funding_rate, mfe_r)
        return ProcessResult(closed=closed)

    async def _update_stop_stage(
        self, position: VirtualPosition, candles: list[OHLCVCandle], last_price: Decimal
    ) -> StopMove | None:
        """Пересчитывает стадию управляемого стопа и персистит её; при ПЕРЕХОДЕ возвращает StopMove.

        Стадия (INITIAL/BREAKEVEN/TRAILING) хранится в БД, поэтому переживает рестарт движка —
        алерт (его шлёт вызывающий по StopMove) идёт строго на смену стадии, а не при каждом старте.
        """
        stop, reason = current_managed_stop(
            position.side,
            position.entry_price,
            position.stop_price,
            candles,
            position.entry_ts,
            settings.BREAKEVEN_TRIGGER_R,
            settings.TRAIL_ACTIVATION_R,
            settings.TRAIL_DISTANCE_R,
        )
        stage = _STAGE_BY_REASON.get(reason, StopStage.INITIAL)
        if stage == position.stop_stage:
            return None
        position.stop_stage = stage
        await self._positions.save(position)
        if stage == StopStage.INITIAL:
            return None
        return StopMove(position=position, reason=reason, stop=stop, mark=last_price)

    async def _find_exit(
        self,
        position: VirtualPosition,
        candles: list[OHLCVCandle],
        funding_rate: float,
        last_price: Decimal,
    ) -> tuple[ExitOutcome | None, float]:
        outcome, mfe_r = walk_managed_exit(
            position.side,
            position.entry_price,
            position.stop_price,
            position.target_price,
            candles,
            position.entry_ts,
            settings.BREAKEVEN_TRIGGER_R,
            settings.TRAIL_ACTIVATION_R,
            settings.TRAIL_DISTANCE_R,
        )
        if outcome is not None:
            return outcome, mfe_r

        now = utcnow()
        if position.symbol not in self._universe:
            return ExitOutcome(ExitReason.DELISTED, last_price, now), mfe_r
        if abs(funding_rate) >= settings.FUNDING_KILL_SWITCH_PCT:
            return ExitOutcome(ExitReason.EXTREME_FUNDING, last_price, now), mfe_r
        valid_hours = await self._valid_hours(position.entry_signal_id)
        if valid_hours is not None and is_expired(position.entry_ts, valid_hours, now):
            return ExitOutcome(ExitReason.EXPIRED, last_price, now), mfe_r
        return None, mfe_r

    async def _close(
        self,
        account: Account,
        position: VirtualPosition,
        outcome: ExitOutcome,
        funding_rate: float,
        mfe_r: float,
    ) -> ClosedTrade:
        """Закрывает позицию в БД (позиция + баланс + событие, атомарно) и считает PnL.

        Побочки (Telegram-карточка, запись исхода в research) НЕ выполняет — возвращает
        ClosedTrade, по которому вызывающий диспатчит их ПОСЛЕ коммита (без дублей при откате).
        """
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
            update_peak=True,
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
        return ClosedTrade(
            position=position,
            new_balance=account.current_balance,
            exit_price=outcome.price,
            exit_ts=outcome.ts,
            exit_reason=outcome.reason,
            realized_pnl=pnl,
            fees=fees,
            funding=funding,
            mfe_r=mfe_r,
        )

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
            update_peak=False,
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
