from decimal import Decimal
from typing import cast

from sqlmodel.ext.asyncio.session import AsyncSession

from app.domain.risk.models import PortfolioState
from core.settings import settings
from db.models import Account, PositionSide
from db.repositories.account_repo import AccountRepo
from db.repositories.virtual_position_repo import VirtualPositionRepo


async def ensure_default_account(session: AsyncSession) -> Account:
    """Возвращает дефолтный paper-аккаунт, создавая его при первом запуске."""
    repo = AccountRepo(session)
    account = await repo.get_by_name(settings.DEFAULT_ACCOUNT_NAME)
    if account is None:
        account = await repo.create(
            name=settings.DEFAULT_ACCOUNT_NAME,
            initial_balance=Decimal(settings.DEFAULT_INITIAL_BALANCE),
        )
    return account


async def build_portfolio_state(
    session: AsyncSession, account: Account
) -> PortfolioState:
    """Снимок портфеля (открытые позиции по сторонам + equity/peak) для PM."""
    positions = await VirtualPositionRepo(session).list_open(cast(int, account.id))
    longs = sum(1 for position in positions if position.side == PositionSide.LONG)
    shorts = sum(1 for position in positions if position.side == PositionSide.SHORT)
    return PortfolioState(
        equity=account.equity,
        peak_nav=account.peak_nav,
        open_count=len(positions),
        long_count=longs,
        short_count=shorts,
    )
