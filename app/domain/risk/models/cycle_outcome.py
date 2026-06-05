from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from db.models import ExitReason, VirtualPosition


@dataclass
class ClosedTrade:
    position: VirtualPosition
    new_balance: Decimal
    exit_price: Decimal
    exit_ts: datetime
    exit_reason: ExitReason
    realized_pnl: Decimal
    fees: Decimal
    funding: Decimal
    mfe_r: float


@dataclass
class StopMove:
    position: VirtualPosition
    reason: ExitReason
    stop: Decimal
    mark: Decimal


@dataclass
class ProcessResult:
    closed: ClosedTrade | None = None
    stop_move: StopMove | None = None
    mark: Decimal | None = None


@dataclass
class CycleOutcome:
    closed_trades: list[ClosedTrade] = field(default_factory=list)
    stop_moves: list[StopMove] = field(default_factory=list)
