from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from db.models import (
    Direction,
    EventType,
    ExitReason,
    PositionSide,
    PositionState,
    Signal,
    SignalSource,
    VirtualPosition,
)
from db.repositories.account_repo import AccountRepo
from db.repositories.event_repo import EventRepo
from db.repositories.signal_repo import SignalRepo
from db.repositories.virtual_position_repo import VirtualPositionRepo


@pytest.mark.unit
async def test_account_repo_create_and_lookup(session: AsyncSession) -> None:
    repo = AccountRepo(session)
    account = await repo.create(name="primary", initial_balance=Decimal("5000"))
    await session.commit()

    by_id = await repo.get(account.id)
    by_name = await repo.get_by_name("primary")
    assert by_id is not None and by_name is not None
    assert by_id.id == by_name.id == account.id
    assert by_id.current_balance == Decimal("5000")
    assert by_id.peak_nav == Decimal("5000")


@pytest.mark.unit
async def test_account_repo_update_balances_tracks_peak(session: AsyncSession) -> None:
    repo = AccountRepo(session)
    account = await repo.create(name="peak", initial_balance=Decimal("1000"))
    await repo.update_balances(
        account, current_balance=Decimal("900"), equity=Decimal("1200")
    )
    await repo.update_balances(
        account, current_balance=Decimal("800"), equity=Decimal("900")
    )
    await session.commit()

    refreshed = await repo.get(account.id)
    assert refreshed is not None
    assert refreshed.equity == Decimal("900")
    assert refreshed.peak_nav == Decimal("1200")


@pytest.mark.unit
async def test_signal_repo_dedup_lookup(session: AsyncSession) -> None:
    repo = SignalRepo(session)
    bar = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    sig = Signal(
        bar_close_ts=bar,
        symbol="BTC/USDT:USDT",
        source=SignalSource.SCREENER,
        direction=Direction.LONG,
    )
    await repo.create(sig)
    await session.commit()

    found = await repo.get_by_symbol_bar("BTC/USDT:USDT", bar)
    not_found = await repo.get_by_symbol_bar(
        "BTC/USDT:USDT", datetime(2026, 1, 1, 16, 0, tzinfo=timezone.utc)
    )
    assert found is not None and found.id == sig.id
    assert not_found is None


@pytest.mark.unit
async def test_virtual_position_repo_open_close_cycle(session: AsyncSession) -> None:
    account_repo = AccountRepo(session)
    signal_repo = SignalRepo(session)
    pos_repo = VirtualPositionRepo(session)

    account = await account_repo.create(name="cycle", initial_balance=Decimal("10000"))
    signal = await signal_repo.create(
        Signal(
            bar_close_ts=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
            symbol="ETH/USDT:USDT",
            source=SignalSource.SCREENER,
            direction=Direction.LONG,
        )
    )
    pos = await pos_repo.create(
        VirtualPosition(
            account_id=account.id,
            symbol="ETH/USDT:USDT",
            side=PositionSide.LONG,
            state=PositionState.OPEN,
            entry_signal_id=signal.id,
            entry_ts=datetime(2026, 1, 1, 12, 5, tzinfo=timezone.utc),
            entry_price=Decimal("2000"),
            qty=Decimal("0.5"),
            stop_price=Decimal("1950"),
            target_price=Decimal("2100"),
        )
    )

    open_positions = await pos_repo.list_open(account.id)
    assert len(open_positions) == 1

    await pos_repo.close(
        pos,
        exit_ts=datetime(2026, 1, 1, 16, 0, tzinfo=timezone.utc),
        exit_price=Decimal("2100"),
        exit_reason=ExitReason.TARGET,
        realized_pnl=Decimal("50"),
        simulated_fees=Decimal("0.5"),
        simulated_funding=Decimal("0"),
    )
    await session.commit()

    open_positions_after = await pos_repo.list_open(account.id)
    assert open_positions_after == []
    reloaded = await pos_repo.get(pos.id)
    assert reloaded is not None
    assert reloaded.state == PositionState.CLOSED
    assert reloaded.realized_pnl == Decimal("50")


@pytest.mark.unit
async def test_event_repo_append_and_filter(session: AsyncSession) -> None:
    repo = EventRepo(session)
    await repo.append(
        event_type=EventType.SIGNAL_GENERATED,
        entity_type="signal",
        entity_id=1,
        payload={"score": 7},
    )
    await repo.append(
        event_type=EventType.POSITION_OPENED,
        entity_type="position",
        entity_id=42,
        payload={"qty": "0.5"},
    )
    await session.commit()

    signal_events = await repo.list_by_entity("signal", 1)
    pos_events = await repo.list_by_entity("position", 42)
    assert len(signal_events) == 1
    assert signal_events[0].payload_json == {"score": 7}
    assert len(pos_events) == 1
    assert pos_events[0].event_type == EventType.POSITION_OPENED
