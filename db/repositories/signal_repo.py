from datetime import datetime

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from db.models import Signal


class SignalRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, signal: Signal) -> Signal:
        self._session.add(signal)
        await self._session.flush()
        return signal

    async def get(self, signal_id: int) -> Signal | None:
        return await self._session.get(Signal, signal_id)

    async def get_by_symbol_bar(
        self, symbol: str, bar_close_ts: datetime
    ) -> Signal | None:
        result = await self._session.exec(
            select(Signal).where(
                Signal.symbol == symbol, Signal.bar_close_ts == bar_close_ts
            )
        )
        return result.first()

    async def list_recent(self, limit: int = 50) -> list[Signal]:
        result = await self._session.exec(
            select(Signal).order_by(col(Signal.ts).desc()).limit(limit)
        )
        return list(result.all())
