"""add leverage and margin to virtual_position

Revision ID: ffdfd1dea751
Revises: dcdf77794a05
Create Date: 2026-05-27 09:05:24.160906+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
import db.types


revision: str = "ffdfd1dea751"
down_revision: str | Sequence[str] | None = "dcdf77794a05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "virtual_position", sa.Column("leverage", sa.Integer(), nullable=True)
    )
    op.add_column(
        "virtual_position", sa.Column("margin", db.types.DecimalText(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("virtual_position", "margin")
    op.drop_column("virtual_position", "leverage")
