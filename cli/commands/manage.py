import asyncio
from decimal import Decimal
from typing import Literal, cast

import typer

from app.clients.ccxt.client import CcxtClient
from app.models.setup import CryptoSetup, FinalSignal
from app.portfolio.account_service import ensure_default_account
from app.portfolio.manager import PortfolioManager
from app.portfolio.watcher import PositionWatcher
from db._time import utcnow
from db.engine import session_scope
from db.models import (
    Decision,
    Direction,
    ExitReason,
    PositionState,
    Signal,
    SignalSource,
)
from db.repositories.account_repo import AccountRepo
from db.repositories.signal_repo import SignalRepo
from db.repositories.system_state_repo import SystemStateRepo
from db.repositories.virtual_position_repo import VirtualPositionRepo

_MANUAL_SETUP_TYPE = "manual"
_MANUAL_VALID_HOURS = 24


async def _set_halt(halted: bool, reason: str | None) -> None:
    async with session_scope() as session:
        await SystemStateRepo(session).set_halted(halted=halted, reason=reason)


def halt_trading(
    reason: str = typer.Option("", "--reason", help="Why trading is paused"),
) -> None:
    """Pause new entries (PortfolioManager will mark signals NO_TRADE/trading_halted)."""
    asyncio.run(_set_halt(halted=True, reason=reason or None))
    typer.echo("trading halted")


def resume_trading() -> None:
    """Resume new entries after a halt."""
    asyncio.run(_set_halt(halted=False, reason=None))
    typer.echo("trading resumed")


async def _account_create(name: str, balance: int) -> int:
    async with session_scope() as session:
        repo = AccountRepo(session)
        if await repo.get_by_name(name):
            raise typer.BadParameter(f"account '{name}' already exists")
        account = await repo.create(name=name, initial_balance=Decimal(balance))
        return cast(int, account.id)


def account_create(
    name: str = typer.Option(..., "--name", help="Account name"),
    balance: int = typer.Option(..., "--balance", min=1, help="Initial USDT balance"),
) -> None:
    """Create a paper-trading account."""
    account_id = asyncio.run(_account_create(name=name, balance=balance))
    typer.echo(f"account created id={account_id} name={name} balance={balance}")


async def _force_close(position_id: int) -> str | None:
    async with session_scope() as session, CcxtClient() as ccxt:
        positions = VirtualPositionRepo(session)
        position = await positions.get(position_id)
        if position is None or position.state != PositionState.OPEN:
            return None
        account = await ensure_default_account(session)
        candles = await ccxt.fetch_ohlcv(position.symbol, timeframe="4h", limit=1)
        price = Decimal(str(candles[-1].close)) if candles else position.entry_price
        watcher = PositionWatcher(session=session, ccxt=ccxt, universe_symbols=set())
        pnl = await watcher.force_close(
            account=account, position=position, price=price, reason=ExitReason.MANUAL
        )
        return str(pnl)


def force_close(
    position_id: int = typer.Option(..., "--position-id", help="VirtualPosition id"),
) -> None:
    """Force-close an open position at the latest 4h close price."""
    pnl = asyncio.run(_force_close(position_id))
    if pnl is None:
        typer.echo("no open position with that id")
        raise typer.Exit(code=1)
    typer.echo(f"position {position_id} closed, realized_pnl={pnl}")


async def _manual_signal(
    symbol: str, side: str, entry: float, stop: float, target: float
) -> str:
    direction = cast(Literal["long", "short"], side)
    risk_reward = abs(target - entry) / abs(entry - stop) if entry != stop else 0.0
    final = FinalSignal(
        symbol=symbol,
        direction=direction,
        setup_type=_MANUAL_SETUP_TYPE,
        entry_price=entry,
        stop_price=stop,
        target_price=target,
        risk_reward=risk_reward,
        valid_hours=_MANUAL_VALID_HOURS,
        confluence_score=1.0,
        invalidation=f"manual close beyond {stop}",
        thesis="manual signal (screener bypass)",
        key_risks=[],
        leverage_intent="conservative",
    )
    setup = CryptoSetup(
        direction=direction,
        setup_type=_MANUAL_SETUP_TYPE,
        entry_price=entry,
        stop_price=stop,
        target_price=target,
        risk_reward=risk_reward,
        valid_hours=_MANUAL_VALID_HOURS,
        funding_impact_pct=0.0,
        invalidation=final.invalidation,
        leverage_intent="conservative",
    )
    bar_close = utcnow()

    async with session_scope() as session, CcxtClient() as ccxt:
        account = await ensure_default_account(session)
        funding = await ccxt.fetch_funding_rate_history(symbol, limit=1)
        rate = funding[-1].funding_rate if funding else 0.0
        signal = await SignalRepo(session).create(
            Signal(
                symbol=symbol,
                bar_close_ts=bar_close,
                source=SignalSource.MANUAL,
                direction=Direction(side),
                decision=Decision.NO_TRADE,
                decision_reason=_MANUAL_SETUP_TYPE,
                crypto_setup_json=setup.model_dump(mode="json"),
            )
        )
        decision = await PortfolioManager(session).evaluate(
            account=account,
            signal_id=cast(int, signal.id),
            final_signal=final,
            funding_rate=rate,
            bar_close_ts=bar_close,
        )
        signal.decision = decision
        signal.decision_reason = decision.value
        return decision.value


def manual_signal(
    symbol: str = typer.Option(..., "--symbol", help="ccxt symbol, e.g. BTC/USDT:USDT"),
    side: str = typer.Option(..., "--side", help="long | short"),
    entry: float = typer.Option(..., "--entry"),
    stop: float = typer.Option(..., "--stop"),
    target: float = typer.Option(..., "--target"),
) -> None:
    """Submit a manual signal (bypass screener) through PortfolioManager risk checks."""
    if side not in ("long", "short"):
        raise typer.BadParameter("side must be 'long' or 'short'")
    decision = asyncio.run(
        _manual_signal(symbol=symbol, side=side, entry=entry, stop=stop, target=target)
    )
    typer.echo(f"manual signal decision: {decision}")
