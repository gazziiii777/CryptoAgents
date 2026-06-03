"""add breakeven and trailing_stop to virtual_position.exit_reason enum

Revision ID: c7d2e9f4a1b8
Revises: ffdfd1dea751
Create Date: 2026-06-03 21:55:00.000000+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "c7d2e9f4a1b8"
down_revision: str | Sequence[str] | None = "ffdfd1dea751"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ENUM_WITH_MANAGED_EXITS = (
    "ENUM('STOP','TARGET','INVALIDATION','EXPIRED','MANUAL',"
    "'EXTREME_FUNDING','DELISTED','BREAKEVEN','TRAILING_STOP')"
)
_ENUM_ORIGINAL = (
    "ENUM('STOP','TARGET','INVALIDATION','EXPIRED','MANUAL',"
    "'EXTREME_FUNDING','DELISTED')"
)


def upgrade() -> None:
    op.execute(
        "ALTER TABLE virtual_position MODIFY COLUMN exit_reason "
        f"{_ENUM_WITH_MANAGED_EXITS} DEFAULT NULL"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE virtual_position MODIFY COLUMN exit_reason "
        f"{_ENUM_ORIGINAL} DEFAULT NULL"
    )
