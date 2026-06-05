"""add stop_stage to virtual_position

Revision ID: b3e4f1a2c9d0
Revises: c7d2e9f4a1b8
Create Date: 2026-06-05 16:00:00.000000+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b3e4f1a2c9d0"
down_revision: str | Sequence[str] | None = "c7d2e9f4a1b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "virtual_position",
        sa.Column(
            "stop_stage",
            sa.Enum("INITIAL", "BREAKEVEN", "TRAILING", name="stopstage"),
            nullable=False,
            server_default="INITIAL",
        ),
    )


def downgrade() -> None:
    op.drop_column("virtual_position", "stop_stage")
