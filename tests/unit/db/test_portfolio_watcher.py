from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.clients.ccxt.models import FundingRateHistoryEntry, OHLCVCandle
from app.domain.models.setup import CryptoSetup
from app.services.positions.watcher import PositionWatcher
from core.constants.time import MS_PER_SECOND
from db.models import (
    Account,
    Direction,
    PositionSide,
    PositionState,
    Signal,
    VirtualPosition,
)
from db._time import utcnow
from db.repositories.account_repo import AccountRepo
from db.repositories.signal_repo import SignalRepo
from db.repositories.virtual_position_repo import VirtualPositionRepo

_SYMBOL = "BTC/USDT:USDT"
_ENTRY_TS = datetime(2026, 1, 1, tzinfo=timezone.utc)
_CRYPTO_SETUP = CryptoSetup(
    direction="long",
    setup_type="breakout",
    entry_price=100.0,
    stop_price=95.0,
    target_price=110.0,
    risk_reward=2.0,
    valid_hours=24,
    funding_impact_pct=0.0,
    invalidation="4h close below 95",
    leverage_intent="moderate",
)


class _FakeCcxt:
    def __init__(self, candles: list[OHLCVCandle], funding: float = 0.0) -> None:
        self._candles = candles
        self._funding = funding

    async def fetch_ohlcv(
        self, symbol: str, timeframe: str = "4h", limit: int = 100
    ) -> list[OHLCVCandle]:
        return self._candles

    async def fetch_funding_rate_history(
        self, symbol: str, limit: int = 1
    ) -> list[FundingRateHistoryEntry]:
        return [FundingRateHistoryEntry(timestamp=0, funding_rate=self._funding)]


def _candle(ts: datetime, high: float, low: float) -> OHLCVCandle:
    return OHLCVCandle(
        timestamp=int(ts.timestamp() * MS_PER_SECOND),
        open=low,
        high=high,
        low=low,
        close=(high + low) / 2,
        volume=1.0,
    )


async def _setup_open_position(
    session: AsyncSession, entry_ts: datetime = _ENTRY_TS
) -> Account:
    account = await AccountRepo(session).create(
        name="paper", initial_balance=Decimal("2000")
    )
    signal = await SignalRepo(session).create(
        Signal(
            symbol=_SYMBOL,
            bar_close_ts=entry_ts,
            direction=Direction.LONG,
            crypto_setup_json=_CRYPTO_SETUP.model_dump(mode="json"),
        )
    )
    await VirtualPositionRepo(session).create(
        VirtualPosition(
            account_id=account.id,  # type: ignore[arg-type]
            symbol=_SYMBOL,
            side=PositionSide.LONG,
            entry_signal_id=signal.id,  # type: ignore[arg-type]
            entry_ts=entry_ts,
            entry_price=Decimal("100"),
            qty=Decimal("4"),
            stop_price=Decimal("95"),
            target_price=Decimal("110"),
        )
    )
    return account


@pytest.mark.unit
async def test_watcher_closes_on_target_and_credits_pnl(session: AsyncSession) -> None:
    account = await _setup_open_position(session)
    candle = _candle(datetime(2026, 1, 1, 4, tzinfo=timezone.utc), high=111, low=105)
    watcher = PositionWatcher(session, _FakeCcxt([candle]), {_SYMBOL})  # type: ignore[arg-type]

    closed = await watcher.run(account)

    assert len(closed.closed_trades) == 1
    position = await VirtualPositionRepo(session).list_open(account.id)  # type: ignore[arg-type]
    assert position == []
    assert account.current_balance > Decimal("2000")


@pytest.mark.unit
async def test_watcher_delists_when_symbol_left_universe(session: AsyncSession) -> None:
    account = await _setup_open_position(session)
    candle = _candle(datetime(2026, 1, 1, 4, tzinfo=timezone.utc), high=101, low=99)
    watcher = PositionWatcher(session, _FakeCcxt([candle]), set())  # type: ignore[arg-type]

    closed = await watcher.run(account)

    assert len(closed.closed_trades) == 1
    repo = VirtualPositionRepo(session)
    closed_positions = [
        p
        for p in await repo.list_open(account.id)  # type: ignore[arg-type]
        if p.state == PositionState.OPEN
    ]
    assert closed_positions == []


@pytest.mark.unit
async def test_watcher_keeps_open_when_no_exit(session: AsyncSession) -> None:
    entry_ts = utcnow()
    account = await _setup_open_position(session, entry_ts=entry_ts)
    candle = _candle(entry_ts, high=105, low=99)
    watcher = PositionWatcher(session, _FakeCcxt([candle]), {_SYMBOL})  # type: ignore[arg-type]

    closed = await watcher.run(account)

    assert len(closed.closed_trades) == 0
    positions = await VirtualPositionRepo(session).list_open(account.id)  # type: ignore[arg-type]
    assert len(positions) == 1


@pytest.mark.unit
async def test_watcher_no_candles_does_not_count_as_closed(
    session: AsyncSession,
) -> None:
    account = await _setup_open_position(session, entry_ts=utcnow())
    watcher = PositionWatcher(session, _FakeCcxt([]), {_SYMBOL})  # type: ignore[arg-type]

    closed = await watcher.run(account)

    assert len(closed.closed_trades) == 0
    positions = await VirtualPositionRepo(session).list_open(account.id)  # type: ignore[arg-type]
    assert len(positions) == 1


@pytest.mark.unit
async def test_watcher_does_not_raise_peak_on_unrealized_gain(
    session: AsyncSession,
) -> None:
    entry_ts = utcnow()
    account = await _setup_open_position(session, entry_ts=entry_ts)
    candle = _candle(entry_ts, high=108, low=104)
    watcher = PositionWatcher(session, _FakeCcxt([candle]), {_SYMBOL})  # type: ignore[arg-type]

    await watcher.run(account)

    assert account.equity > Decimal("2000")
    assert account.peak_nav == Decimal("2000")


@pytest.mark.unit
async def test_watcher_raises_peak_on_realized_profit(session: AsyncSession) -> None:
    account = await _setup_open_position(session)
    candle = _candle(datetime(2026, 1, 1, 4, tzinfo=timezone.utc), high=111, low=105)
    watcher = PositionWatcher(session, _FakeCcxt([candle]), {_SYMBOL})  # type: ignore[arg-type]

    await watcher.run(account)

    assert account.peak_nav > Decimal("2000")
