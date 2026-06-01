from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from core.settings import settings
from db import models  # noqa: F401 — registers tables on metadata


@pytest.fixture(autouse=True)
def _disable_telegram(monkeypatch: pytest.MonkeyPatch) -> None:
    """Глушит Telegram во всех тестах: portfolio-тесты открывают/закрывают позиции и
    дёрнули бы реальный notify, если в локальном .env задан токен бота.
    """
    disabled = settings.model_copy(
        update={"TELEGRAM_BOT_TOKEN": None, "TELEGRAM_CHAT_ID": None}
    )
    monkeypatch.setattr("app.notifications.positions.settings", disabled)


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """In-memory SQLite per test. Single connection — иначе :memory: создаёт новую БД на каждый коннект."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", connect_args={"check_same_thread": False}
    )

    async with engine.begin() as conn:
        await conn.exec_driver_sql("PRAGMA foreign_keys=ON")
        await conn.run_sync(SQLModel.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as s:
        yield s

    await engine.dispose()
