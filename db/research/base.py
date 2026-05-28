from sqlalchemy.orm import DeclarativeBase


class ResearchBase(DeclarativeBase):
    """Отдельная metadata research-БД (схема `research`), вне SQLModel.metadata и alembic."""
