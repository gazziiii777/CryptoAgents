import itertools
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.setup import FinalSignal
from app.portfolio.manager import PortfolioManager
from db.models import (
    Account,
    Decision,
    Direction,
    PositionSide,
    Signal,
    VirtualPosition,
)
from db.repositories.account_repo import AccountRepo
from db.repositories.signal_repo import SignalRepo
from db.repositories.virtual_position_repo import VirtualPositionRepo

_BAR_TS = datetime(2026, 1, 1, tzinfo=timezone.utc)
_TS_COUNTER = itertools.count()


@pytest.fixture(autouse=True)
def _reset_ts_counter() -> None:
    """Свежий счётчик на каждый тест — без переноса состояния между тестами."""
    global _TS_COUNTER
    _TS_COUNTER = itertools.count()


def _unique_ts() -> datetime:
    return _BAR_TS + timedelta(seconds=next(_TS_COUNTER))


def _final(symbol: str = "BTC/USDT:USDT", direction: str = "long") -> FinalSignal:
    return FinalSignal(
        symbol=symbol,
        direction=direction,  # type: ignore[arg-type]
        setup_type="trend_continuation",
        entry_price=100.0,
        stop_price=95.0,
        target_price=110.0,
        risk_reward=2.0,
        valid_hours=24,
        confluence_score=0.8,
        invalidation="x",
        thesis="t",
        key_risks=[],
        leverage_intent="moderate",
    )


async def _account(session: AsyncSession) -> Account:
    return await AccountRepo(session).create(
        name="paper", initial_balance=Decimal("2000")
    )


async def _signal_id(session: AsyncSession, symbol: str = "BTC/USDT:USDT") -> int:
    signal = await SignalRepo(session).create(
        Signal(symbol=symbol, bar_close_ts=_unique_ts(), direction=Direction.LONG)
    )
    assert signal.id is not None
    return signal.id


async def _open(
    session: AsyncSession, account_id: int, symbol: str, side: PositionSide
) -> None:
    signal_id = await _signal_id(session, symbol)
    await VirtualPositionRepo(session).create(
        VirtualPosition(
            account_id=account_id,
            symbol=symbol,
            side=side,
            entry_signal_id=signal_id,
            entry_ts=_BAR_TS,
            entry_price=Decimal("100"),
            qty=Decimal("1"),
            stop_price=Decimal("95"),
            target_price=Decimal("110"),
        )
    )


@pytest.mark.unit
async def test_taken_opens_position(session: AsyncSession) -> None:
    account = await _account(session)
    signal_id = await _signal_id(session)
    manager = PortfolioManager(session)

    decision = await manager.evaluate(
        account=account,
        signal_id=signal_id,
        final_signal=_final(),
        funding_rate=0.0001,
        bar_close_ts=_BAR_TS,
    )

    assert decision == Decision.TAKEN
    positions = await VirtualPositionRepo(session).list_open(account.id)  # type: ignore[arg-type]
    assert len(positions) == 1
    position = positions[0]
    assert position.qty > Decimal("0")
    assert position.side == PositionSide.LONG
    # P8: leverage from (trend_continuation, moderate) = 5; margin = notional / leverage
    assert position.leverage == 5
    assert position.margin is not None
    assert position.notional is not None
    assert position.margin == pytest.approx(position.notional / Decimal(5))


@pytest.mark.unit
async def test_dedup_skips_existing_symbol(session: AsyncSession) -> None:
    account = await _account(session)
    await _open(session, account.id, "BTC/USDT:USDT", PositionSide.LONG)  # type: ignore[arg-type]
    signal_id = await _signal_id(session, "BTC/USDT:USDT")

    decision = await PortfolioManager(session).evaluate(
        account=account,
        signal_id=signal_id,
        final_signal=_final(),
        funding_rate=0.0001,
        bar_close_ts=_BAR_TS,
    )
    assert decision == Decision.SKIPPED_DEDUP


@pytest.mark.unit
async def test_same_direction_cap(session: AsyncSession) -> None:
    account = await _account(session)
    await _open(session, account.id, "AAA/USDT:USDT", PositionSide.LONG)  # type: ignore[arg-type]
    await _open(session, account.id, "BBB/USDT:USDT", PositionSide.LONG)  # type: ignore[arg-type]
    signal_id = await _signal_id(session, "CCC/USDT:USDT")

    decision = await PortfolioManager(session).evaluate(
        account=account,
        signal_id=signal_id,
        final_signal=_final(symbol="CCC/USDT:USDT", direction="long"),
        funding_rate=0.0001,
        bar_close_ts=_BAR_TS,
    )
    assert decision == Decision.SKIPPED_SLOT


@pytest.mark.unit
async def test_funding_kill_switch(session: AsyncSession) -> None:
    account = await _account(session)
    signal_id = await _signal_id(session)

    decision = await PortfolioManager(session).evaluate(
        account=account,
        signal_id=signal_id,
        final_signal=_final(),
        funding_rate=0.003,
        bar_close_ts=_BAR_TS,
    )
    assert decision == Decision.SKIPPED_FUNDING


@pytest.mark.unit
async def test_drawdown_breaker(session: AsyncSession) -> None:
    account = await _account(session)
    await AccountRepo(session).update_balances(
        account, current_balance=Decimal("1700"), equity=Decimal("1700")
    )
    signal_id = await _signal_id(session)

    decision = await PortfolioManager(session).evaluate(
        account=account,
        signal_id=signal_id,
        final_signal=_final(),
        funding_rate=0.0001,
        bar_close_ts=_BAR_TS,
    )
    assert decision == Decision.SKIPPED_DRAWDOWN
