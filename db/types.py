from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, Dialect, Text, TypeDecorator


class DecimalText(TypeDecorator[Decimal]):
    """Decimal stored as TEXT — preserves exact precision across SQLite and Postgres.

    Float storage would lose precision on round-trip and is forbidden for monetary
    fields. TEXT is the portable choice; on Postgres migration this can switch to
    NUMERIC via a single TypeDecorator edit without touching call sites.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(
        self, value: Decimal | int | str | None, dialect: Dialect
    ) -> str | None:
        if value is None:
            return None
        if not isinstance(value, Decimal):
            value = Decimal(str(value))
        return format(value, "f")

    def process_result_value(
        self, value: str | None, dialect: Dialect
    ) -> Decimal | None:
        if value is None:
            return None
        return Decimal(value)


class UTCDateTime(TypeDecorator[datetime]):
    """Datetime that rejects naive values and always normalises to UTC.

    SQLite drops tz info on storage, so on read we re-attach UTC. Naive datetimes
    are rejected at bind time — they're almost always a bug in this codebase
    (mixing local time and UTC silently corrupts time-series joins).
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
