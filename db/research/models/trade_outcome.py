from datetime import datetime

from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from db.research.base import ResearchBase
from db.types import UTCDateTime


class TradeOutcome(ResearchBase):
    """Исход закрытой позиции, связанный с сигналом: PnL, R-multiple, время в сделке.

    Цены/PnL хранятся как Float намеренно: это аналитическая research-БД, не
    system-of-record. Точные денежные значения живут в торговой БД (DecimalText).
    Не сверять эти числа с торговой БД — float-округление неизбежно разойдётся.
    """

    __tablename__ = "trade_outcome"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    signal_record_id: Mapped[int | None] = mapped_column(Integer, index=True)
    trading_signal_id: Mapped[int | None] = mapped_column(Integer, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[str] = mapped_column(String(8))
    setup_type: Mapped[str | None] = mapped_column(String(32))
    leverage: Mapped[int | None] = mapped_column(Integer)

    entry_price: Mapped[float] = mapped_column(Float)
    exit_price: Mapped[float] = mapped_column(Float)
    stop_price: Mapped[float] = mapped_column(Float)
    target_price: Mapped[float] = mapped_column(Float)
    exit_reason: Mapped[str] = mapped_column(String(24), index=True)

    realized_pnl: Mapped[float] = mapped_column(Float)
    r_multiple: Mapped[float] = mapped_column(Float)
    holding_hours: Mapped[float] = mapped_column(Float)
    simulated_fees: Mapped[float] = mapped_column(Float)
    simulated_funding: Mapped[float] = mapped_column(Float)

    entry_ts: Mapped[datetime] = mapped_column(UTCDateTime)
    exit_ts: Mapped[datetime] = mapped_column(UTCDateTime)
