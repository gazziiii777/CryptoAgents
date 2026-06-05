from datetime import datetime
from decimal import Decimal

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from db.models import ExitReason, PositionState, VirtualPosition


class VirtualPositionRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, position: VirtualPosition) -> VirtualPosition:
        self._session.add(position)
        await self._session.flush()
        return position

    async def save(self, position: VirtualPosition) -> None:
        self._session.add(position)
        await self._session.flush()

    async def get(self, position_id: int) -> VirtualPosition | None:
        return await self._session.get(VirtualPosition, position_id)

    async def list_open(self, account_id: int) -> list[VirtualPosition]:
        result = await self._session.exec(
            select(VirtualPosition).where(
                VirtualPosition.account_id == account_id,
                VirtualPosition.state == PositionState.OPEN,
            )
        )
        return list(result.all())

    async def list_recent_closed(
        self, account_id: int, limit: int = 50
    ) -> list[VirtualPosition]:
        result = await self._session.exec(
            select(VirtualPosition)
            .where(
                VirtualPosition.account_id == account_id,
                VirtualPosition.state == PositionState.CLOSED,
            )
            .order_by(col(VirtualPosition.exit_ts).desc())
            .limit(limit)
        )
        return list(result.all())

    async def get_open_by_symbol(
        self, account_id: int, symbol: str
    ) -> VirtualPosition | None:
        result = await self._session.exec(
            select(VirtualPosition).where(
                VirtualPosition.account_id == account_id,
                VirtualPosition.symbol == symbol,
                VirtualPosition.state == PositionState.OPEN,
            )
        )
        return result.first()

    async def close(
        self,
        position: VirtualPosition,
        *,
        exit_ts: datetime,
        exit_price: Decimal,
        exit_reason: ExitReason,
        realized_pnl: Decimal,
        simulated_fees: Decimal,
        simulated_funding: Decimal,
    ) -> VirtualPosition:
        position.state = PositionState.CLOSED
        position.exit_ts = exit_ts
        position.exit_price = exit_price
        position.exit_reason = exit_reason
        position.realized_pnl = realized_pnl
        position.simulated_fees = simulated_fees
        position.simulated_funding = simulated_funding
        self._session.add(position)
        await self._session.flush()
        return position
