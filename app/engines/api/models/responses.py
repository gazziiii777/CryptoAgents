from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.engines.api.symbols import base_from_ccxt, display_symbol
from app.domain.models.liquidity import LiquidityKind, LiquidityLevel, LiquidityMap
from app.domain.models.liquidations import NormalizedLiquidation
from app.domain.risk.pnl import unrealized_pnl
from db.models import Account, Signal, VirtualPosition
from db.research.models.regime_performance import RegimePerformance

_CAMEL = ConfigDict(populate_by_name=True)


class LiquidityLevelOut(BaseModel):
    price: float
    kind: LiquidityKind
    strength: float

    @classmethod
    def from_domain(cls, source: LiquidityLevel) -> LiquidityLevelOut:
        return cls(price=source.price, kind=source.kind, strength=source.strength)

    @classmethod
    def from_optional(cls, source: LiquidityLevel | None) -> LiquidityLevelOut | None:
        return cls.from_domain(source) if source is not None else None


class LiquidityMapOut(BaseModel):
    model_config = _CAMEL

    symbol: str
    mark_price: float = Field(alias="markPrice")
    walls: list[LiquidityLevelOut]
    liq_clusters: list[LiquidityLevelOut] = Field(alias="liqClusters")
    book_imbalance: float = Field(alias="bookImbalance")
    nearest_magnet_above: LiquidityLevelOut | None = Field(alias="nearestMagnetAbove")
    nearest_magnet_below: LiquidityLevelOut | None = Field(alias="nearestMagnetBelow")

    @classmethod
    def from_domain(cls, domain: LiquidityMap) -> LiquidityMapOut:
        return cls(
            symbol=display_symbol(base_from_ccxt(domain.symbol)),
            mark_price=domain.mark_price,
            walls=[LiquidityLevelOut.from_domain(wall) for wall in domain.walls],
            liq_clusters=[
                LiquidityLevelOut.from_domain(cluster)
                for cluster in domain.liq_clusters
            ],
            book_imbalance=domain.book_imbalance,
            nearest_magnet_above=LiquidityLevelOut.from_optional(
                domain.nearest_magnet_above
            ),
            nearest_magnet_below=LiquidityLevelOut.from_optional(
                domain.nearest_magnet_below
            ),
        )


class SymbolOut(BaseModel):
    model_config = _CAMEL

    symbol: str
    base: str
    mark_price: float = Field(alias="markPrice")


class AccountOut(BaseModel):
    model_config = _CAMEL

    name: str
    base_currency: str = Field(alias="baseCurrency")
    initial_balance: float = Field(alias="initialBalance")
    current_balance: float = Field(alias="currentBalance")
    equity: float
    peak_nav: float = Field(alias="peakNav")
    open_positions: int = Field(alias="openPositions")
    unrealized_pnl: float = Field(alias="unrealizedPnl")
    updated_at: datetime = Field(alias="updatedAt")

    @classmethod
    def from_domain(
        cls, account: Account, *, open_positions: int, unrealized_pnl: float
    ) -> AccountOut:
        return cls(
            name=account.name,
            base_currency=account.base_currency,
            initial_balance=float(account.initial_balance),
            current_balance=float(account.current_balance),
            equity=float(account.equity),
            peak_nav=float(account.peak_nav),
            open_positions=open_positions,
            unrealized_pnl=unrealized_pnl,
            updated_at=account.updated_at,
        )


class PositionOut(BaseModel):
    model_config = _CAMEL

    id: int
    symbol: str
    side: str
    entry_ts: datetime = Field(alias="entryTs")
    entry_price: float = Field(alias="entryPrice")
    qty: float
    notional: float | None
    leverage: int | None
    stop_price: float = Field(alias="stopPrice")
    target_price: float = Field(alias="targetPrice")
    mark_price: float | None = Field(alias="markPrice")
    unrealized_pnl: float | None = Field(alias="unrealizedPnl")
    state: str

    @classmethod
    def from_domain(
        cls, position: VirtualPosition, *, mark_price: float | None
    ) -> PositionOut:
        unrealized = (
            float(
                unrealized_pnl(
                    position.side,
                    position.entry_price,
                    Decimal(str(mark_price)),
                    position.qty,
                )
            )
            if mark_price is not None
            else None
        )
        return cls(
            id=position.id,
            symbol=display_symbol(base_from_ccxt(position.symbol)),
            side=position.side.value,
            entry_ts=position.entry_ts,
            entry_price=float(position.entry_price),
            qty=float(position.qty),
            notional=float(position.notional)
            if position.notional is not None
            else None,
            leverage=position.leverage,
            stop_price=float(position.stop_price),
            target_price=float(position.target_price),
            mark_price=mark_price,
            unrealized_pnl=unrealized,
            state=position.state.value,
        )


class ClosedTradeOut(BaseModel):
    model_config = _CAMEL

    id: int
    symbol: str
    side: str
    entry_ts: datetime = Field(alias="entryTs")
    entry_price: float = Field(alias="entryPrice")
    exit_ts: datetime | None = Field(alias="exitTs")
    exit_price: float | None = Field(alias="exitPrice")
    exit_reason: str | None = Field(alias="exitReason")
    realized_pnl: float | None = Field(alias="realizedPnl")

    @classmethod
    def from_domain(cls, position: VirtualPosition) -> ClosedTradeOut:
        return cls(
            id=position.id,
            symbol=display_symbol(base_from_ccxt(position.symbol)),
            side=position.side.value,
            entry_ts=position.entry_ts,
            entry_price=float(position.entry_price),
            exit_ts=position.exit_ts,
            exit_price=(
                float(position.exit_price) if position.exit_price is not None else None
            ),
            exit_reason=(
                position.exit_reason.value if position.exit_reason is not None else None
            ),
            realized_pnl=(
                float(position.realized_pnl)
                if position.realized_pnl is not None
                else None
            ),
        )


class SignalOut(BaseModel):
    model_config = _CAMEL

    id: int
    ts: datetime
    symbol: str
    source: str
    screener_score: int | None = Field(alias="screenerScore")
    confluence_score: float | None = Field(alias="confluenceScore")
    direction: str
    decision: str
    decision_reason: str | None = Field(alias="decisionReason")
    strategy_version: str = Field(alias="strategyVersion")

    @classmethod
    def from_domain(cls, signal: Signal) -> SignalOut:
        return cls(
            id=signal.id,
            ts=signal.ts,
            symbol=display_symbol(base_from_ccxt(signal.symbol)),
            source=signal.source.value,
            screener_score=signal.screener_score,
            confluence_score=signal.confluence_score,
            direction=signal.direction.value,
            decision=signal.decision.value,
            decision_reason=signal.decision_reason,
            strategy_version=signal.strategy_version,
        )


class LiquidationOut(BaseModel):
    model_config = _CAMEL

    exchange: str
    symbol: str
    side: str
    price: float
    qty: float
    notional: float
    ts: int

    @classmethod
    def from_domain(cls, event: NormalizedLiquidation) -> LiquidationOut:
        return cls(
            exchange=event.exchange,
            symbol=event.symbol,
            side=event.liquidated_side,
            price=event.price,
            qty=event.quantity,
            notional=event.price * event.quantity,
            ts=event.trade_time_ms,
        )


class RegimePerformanceOut(BaseModel):
    model_config = _CAMEL

    regime: str
    trades: int
    win_rate: float = Field(alias="winRate")
    avg_r: float = Field(alias="avgR")
    total_r: float = Field(alias="totalR")
    avg_mfe_r: float | None = Field(alias="avgMfeR")
    avg_holding_hours: float = Field(alias="avgHoldingHours")

    @classmethod
    def from_domain(cls, source: RegimePerformance) -> RegimePerformanceOut:
        return cls(
            regime=source.regime,
            trades=source.trades,
            win_rate=source.win_rate,
            avg_r=source.avg_r,
            total_r=source.total_r,
            avg_mfe_r=source.avg_mfe_r,
            avg_holding_hours=source.avg_holding_hours,
        )
