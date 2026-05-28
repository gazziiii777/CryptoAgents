from decimal import Decimal

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from core.constants.markets import QUOTE_CURRENCY
from db._time import utcnow
from db.models import Account


class AccountRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        name: str,
        initial_balance: Decimal,
        base_currency: str = QUOTE_CURRENCY,
    ) -> Account:
        account = Account(
            name=name,
            base_currency=base_currency,
            initial_balance=initial_balance,
            current_balance=initial_balance,
            equity=initial_balance,
            peak_nav=initial_balance,
        )
        self._session.add(account)
        await self._session.flush()
        return account

    async def get(self, account_id: int) -> Account | None:
        return await self._session.get(Account, account_id)

    async def get_by_name(self, name: str) -> Account | None:
        result = await self._session.exec(select(Account).where(Account.name == name))
        return result.first()

    async def list_all(self) -> list[Account]:
        result = await self._session.exec(select(Account).order_by(col(Account.id)))
        return list(result.all())

    async def update_balances(
        self,
        account: Account,
        *,
        current_balance: Decimal,
        equity: Decimal,
        update_peak: bool = True,
    ) -> Account:
        account.current_balance = current_balance
        account.equity = equity
        if update_peak and equity > account.peak_nav:
            account.peak_nav = equity
        account.updated_at = utcnow()
        self._session.add(account)
        await self._session.flush()
        return account
