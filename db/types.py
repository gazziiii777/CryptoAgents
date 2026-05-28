from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, Dialect, Numeric, String, TypeDecorator
from sqlalchemy.types import TypeEngine

_NUMERIC_PRECISION = 28
_NUMERIC_SCALE = 10
_TEXT_LENGTH = 64


class DecimalText(TypeDecorator[Decimal]):
    """Decimal с точным хранением: TEXT на SQLite, NUMERIC на MariaDB/Postgres.

    SQLite не имеет нативного Decimal — его NUMERIC проходит через float и теряет
    точность, поэтому на нём храним строкой (`format(value, "f")`) и читаем обратно
    в Decimal без потерь. На MariaDB/Postgres — нативный `NUMERIC(28,10)`.
    На уровне Python всегда Decimal in/out. Float для денег запрещён.
    """

    impl = Numeric
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "sqlite":
            return dialect.type_descriptor(String(_TEXT_LENGTH))
        return dialect.type_descriptor(
            Numeric(precision=_NUMERIC_PRECISION, scale=_NUMERIC_SCALE, asdecimal=True)
        )

    def process_bind_param(
        self, value: Decimal | int | str | None, dialect: Dialect
    ) -> Decimal | str | None:
        if value is None:
            return None
        decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
        if dialect.name == "sqlite":
            return format(decimal_value, "f")
        return decimal_value

    def process_result_value(self, value: object, dialect: Dialect) -> Decimal | None:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))


class UTCDateTime(TypeDecorator[datetime]):
    """Datetime that rejects naive values and always normalises to UTC.

    Драйвер возвращает naive datetime (MariaDB DATETIME tz-неосведомлён); на чтении
    приклеиваем UTC. Naive datetime на запись отвергаем — это почти всегда баг
    смешения локального времени и UTC, корруптящий time-series.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError(
                "naive datetime is not allowed; pass timezone-aware UTC datetime"
            )
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc)
