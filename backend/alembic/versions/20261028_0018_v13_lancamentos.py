"""v1.3: compra dividida em categorias

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("expenses") as batch:
        batch.add_column(sa.Column("split_group_id", sa.Uuid(), nullable=True))
        batch.create_index("ix_expenses_split_group_id", ["split_group_id"])


def downgrade() -> None:
    with op.batch_alter_table("expenses") as batch:
        batch.drop_index("ix_expenses_split_group_id")
        batch.drop_column("split_group_id")
