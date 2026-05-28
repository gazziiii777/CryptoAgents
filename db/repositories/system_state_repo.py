from sqlmodel.ext.asyncio.session import AsyncSession

from db._time import utcnow
from db.models import SYSTEM_STATE_ID, SystemState


class SystemStateRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(self) -> SystemState:
        state = await self._session.get(SystemState, SYSTEM_STATE_ID)
        if state is None:
            state = SystemState(id=SYSTEM_STATE_ID)
            self._session.add(state)
            await self._session.flush()
        return state

    async def set_halted(self, *, halted: bool, reason: str | None) -> SystemState:
        state = await self.get_or_create()
        state.halted = halted
        state.halt_reason = reason
        state.updated_at = utcnow()
        self._session.add(state)
        await self._session.flush()
        return state
