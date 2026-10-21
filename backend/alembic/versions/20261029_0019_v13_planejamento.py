"""v1.3: sobra do limite da categoria para o mês seguinte

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("categories") as batch:
        batch.add_column(sa.Column("carry_over", sa.Boolean(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("carry_since", sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("categories") as batch:
        batch.drop_column("carry_since")
        batch.drop_column("carry_over")
