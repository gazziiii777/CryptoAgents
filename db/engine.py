from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from core import settings

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_session_maker: async_sessionmaker[AsyncSession] | None = None


def _apply_sqlite_pragma(dbapi_connection: object, _connection_record: object) -> None:
    """Production-grade PRAGMA на каждый новый коннект SQLite.

    WAL + synchronous=NORMAL — оптимальный durability/performance trade-off для
    one-writer many-readers (scheduler пишет, watcher читает).
    foreign_keys=ON — SQLite по умолчанию игнорирует FK, без этого FK-constraints
    в моделях бесполезны. busy_timeout спасает от SQLITE_BUSY при гонке writer'ов.

    Для aiosqlite dbapi_connection — это AsyncAdapt_aiosqlite_connection, но cursor
    у него синхронный API; внутри он сам пробрасывает выполнение в aiosqlite-поток.
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute(f"PRAGMA busy_timeout={settings.DB_BUSY_TIMEOUT_MS}")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA cache_size=-64000")
        cursor.execute("PRAGMA temp_store=MEMORY")
    finally:
        cursor.close()


def _ensure_db_directory() -> None:
    settings.DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _init() -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    _ensure_db_directory()
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        future=True,
        pool_pre_ping=True,
    )
    event.listen(engine.sync_engine, "connect", _apply_sqlite_pragma)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    logger.info("DB engine initialised: %s", settings.DB_PATH)
    return engine, maker


def get_engine() -> AsyncEngine:
    global _engine, _session_maker
    if _engine is None:
        _engine, _session_maker = _init()
    return _engine


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    global _engine, _session_maker
    if _session_maker is None:
        _engine, _session_maker = _init()
    return _session_maker


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Транзакционный scope: commit при успехе, rollback при исключении."""
    maker = get_session_maker()
    async with maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    global _engine, _session_maker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_maker = None
