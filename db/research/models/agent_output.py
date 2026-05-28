from datetime import datetime

from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.research.base import ResearchBase
from db.types import UTCDateTime


class AgentOutput(ResearchBase):
    """Строка на каждого аналитика на сигнал: его вывод и вклад в синтез."""

    __tablename__ = "agent_output"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    signal_record_id: Mapped[int] = mapped_column(Integer, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    bar_close_ts: Mapped[datetime] = mapped_column(UTCDateTime)
    agent_name: Mapped[str] = mapped_column(String(24), index=True)
    bias: Mapped[str] = mapped_column(String(16))
    confidence: Mapped[float | None] = mapped_column(Float)
    score: Mapped[float | None] = mapped_column(Float)
    key_insight: Mapped[str] = mapped_column(Text)
