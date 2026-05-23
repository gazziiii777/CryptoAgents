from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import StatementError
from sqlmodel.ext.asyncio.session import AsyncSession

from db.models import Account


@pytest.mark.unit
async def test_decimal_round_trip_preserves_precision(session: AsyncSession) -> None:
    """Decimal не должен терять точность: 14 знаков до запятой + 8 после (22 sig figs)."""
    high_precision = Decimal("12345678901234.56789012")
    account = Account(
        name="precision-test",
        initial_balance=high_precision,
        current_balance=high_precision,
        equity=high_precision,
        peak_nav=high_precision,
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)

    loaded = await session.get(Account, account.id)
    assert loaded is not None
    assert loaded.initial_balance == high_precision
    assert isinstance(loaded.initial_balance, Decimal)


@pytest.mark.unit
async def test_decimal_handles_negative_and_zero(session: AsyncSession) -> None:
    account = Account(
        name="zero-neg",
        initial_balance=Decimal("0"),
        current_balance=Decimal("-1234.56"),
        equity=Decimal("0.00000001"),
        peak_nav=Decimal("999999999999"),
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)

    assert account.initial_balance == Decimal("0")
    assert account.current_balance == Decimal("-1234.56")
    assert account.equity == Decimal("0.00000001")


@pytest.mark.unit
async def test_utc_datetime_rejects_naive(session: AsyncSession) -> None:
    """Naive datetime должен ловиться на bind, до записи в БД."""
    naive = datetime(2026, 1, 1, 12, 0, 0)
    account = Account(
        name="naive",
        initial_balance=Decimal("100"),
        current_balance=Decimal("100"),
        equity=Decimal("100"),
        peak_nav=Decimal("100"),
        created_at=naive,
        updated_at=naive,
    )
    session.add(account)
    with pytest.raises(StatementError, match="naive datetime"):
        await session.commit()


@pytest.mark.unit
async def test_utc_datetime_normalises_other_tz_to_utc(session: AsyncSession) -> None:
    """Не-UTC tz сохраняется как UTC, читается обратно с tzinfo=UTC."""
    tokyo = timezone(timedelta(hours=9))
    ts = datetime(2026, 1, 1, 21, 0, 0, tzinfo=tokyo)

    account = Account(
        name="tz-norm",
        initial_balance=Decimal("100"),
        current_balance=Decimal("100"),
        equity=Decimal("100"),
        peak_nav=Decimal("100"),
        created_at=ts,
        updated_at=ts,
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)

    assert account.created_at.tzinfo is timezone.utc
    assert account.created_at == ts.astimezone(timezone.utc)
