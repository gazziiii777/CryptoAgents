from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from db.models import (
    Account,
    Direction,
    ExitReason,
    PositionSide,
    PositionState,
    Signal,
    SignalSource,
    VirtualPosition,
)


async def _make_account(session: AsyncSession, name: str = "main") -> Account:
    account = Account(
        name=name,
        initial_balance=Decimal("10000"),
        current_balance=Decimal("10000"),
        equity=Decimal("10000"),
        peak_nav=Decimal("10000"),
    )
    session.add(account)
    await session.flush()
    return account


def _make_signal(symbol: str, bar_ts: datetime) -> Signal:
    return Signal(
        bar_close_ts=bar_ts,
        symbol=symbol,
        source=SignalSource.SCREENER,
        direction=Direction.LONG,
    )


def _open_position(account_id: int, signal_id: int, symbol: str) -> VirtualPosition:
    return VirtualPosition(
        account_id=account_id,
        symbol=symbol,
        side=PositionSide.LONG,
        state=PositionState.OPEN,
        entry_signal_id=signal_id,
        entry_ts=datetime.now(timezone.utc),
        entry_price=Decimal("100"),
        qty=Decimal("1"),
        stop_price=Decimal("95"),
        target_price=Decimal("110"),
    )


@pytest.mark.unit
async def test_signal_unique_symbol_bar(session: AsyncSession) -> None:
    """Один и тот же (symbol, bar_close_ts) не должен сохраниться дважды."""
    bar = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    session.add(_make_signal("BTC/USDT:USDT", bar))
    await session.commit()

    session.add(_make_signal("BTC/USDT:USDT", bar))
    with pytest.raises(IntegrityError):
        await session.commit()


@pytest.mark.unit
async def test_signal_same_symbol_different_bar_ok(session: AsyncSession) -> None:
    bar1 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    bar2 = datetime(2026, 1, 1, 16, 0, 0, tzinfo=timezone.utc)
    session.add(_make_signal("BTC/USDT:USDT", bar1))
    session.add(_make_signal("BTC/USDT:USDT", bar2))
    await session.commit()


@pytest.mark.unit
async def test_partial_unique_blocks_second_open_same_symbol(
    session: AsyncSession,
) -> None:
    """Нельзя иметь две OPEN-позиции на тот же account+symbol одновременно."""
    account = await _make_account(session)
    signal1 = _make_signal(
        "BTC/USDT:USDT", datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    )
    signal2 = _make_signal(
        "BTC/USDT:USDT", datetime(2026, 1, 1, 16, 0, tzinfo=timezone.utc)
    )
    session.add(signal1)
    session.add(signal2)
    await session.flush()

    session.add(_open_position(account.id, signal1.id, "BTC/USDT:USDT"))
    await session.commit()

    session.add(_open_position(account.id, signal2.id, "BTC/USDT:USDT"))
    with pytest.raises(IntegrityError):
        await session.commit()


@pytest.mark.unit
async def test_partial_unique_allows_open_after_close(session: AsyncSession) -> None:
    """После закрытия первой можно открыть вторую — partial index пускает."""
    account = await _make_account(session)
    signal1 = _make_signal(
        "ETH/USDT:USDT", datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    )
    signal2 = _make_signal(
        "ETH/USDT:USDT", datetime(2026, 1, 1, 16, 0, tzinfo=timezone.utc)
    )
    session.add(signal1)
    session.add(signal2)
    await session.flush()

    pos1 = _open_position(account.id, signal1.id, "ETH/USDT:USDT")
    session.add(pos1)
    await session.flush()

    pos1.state = PositionState.CLOSED
    pos1.exit_ts = datetime(2026, 1, 1, 15, 0, tzinfo=timezone.utc)
    pos1.exit_price = Decimal("110")
    pos1.exit_reason = ExitReason.TARGET
    pos1.realized_pnl = Decimal("10")
    pos1.simulated_fees = Decimal("0.1")
    pos1.simulated_funding = Decimal("0")
    session.add(pos1)
    await session.flush()

    session.add(_open_position(account.id, signal2.id, "ETH/USDT:USDT"))
    await session.commit()


@pytest.mark.unit
async def test_partial_unique_allows_open_on_different_accounts(
    session: AsyncSession,
) -> None:
    account_a = await _make_account(session, "a")
    account_b = await _make_account(session, "b")
    signal_a = _make_signal(
        "SOL/USDT:USDT", datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    )
    signal_b = _make_signal(
        "SOL/USDT:USDT", datetime(2026, 1, 1, 16, 0, tzinfo=timezone.utc)
    )
    session.add(signal_a)
    session.add(signal_b)
    await session.flush()

    session.add(_open_position(account_a.id, signal_a.id, "SOL/USDT:USDT"))
    session.add(_open_position(account_b.id, signal_b.id, "SOL/USDT:USDT"))
    await session.commit()
