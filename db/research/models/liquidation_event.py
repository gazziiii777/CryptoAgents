from datetime import datetime

from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from db.research.base import ResearchBase
from db.types import UTCDateTime


class LiquidationEvent(ResearchBase):
    """Событие принудительной ликвидации с Binance / OKX / Bybit (linear USDT-перпы).

    Сырой поток для будущей калибровки прокси-карты ликвидаций: где реально
    случались ликвидации по цене/времени. order_side — сырая сторона с биржи (у
    каждой своя конвенция); liquidated_side нормализована в long/short.
    """

    __tablename__ = "liquidation_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exchange: Mapped[str] = mapped_column(String(16), index=True, default="binance")
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    order_side: Mapped[str] = mapped_column(String(8))
    liquidated_side: Mapped[str] = mapped_column(String(8), index=True)
    price: Mapped[float] = mapped_column(Float)
    quantity: Mapped[float] = mapped_column(Float)
    notional_usd: Mapped[float] = mapped_column(Float, index=True)
    trade_ts: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
