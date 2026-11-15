"""v1.9.0: avisos por webhook

Revision ID: 0032
Revises: 0031
Create Date: 2026-11-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("webhook_url", sa.String(length=500), nullable=True))
        batch.add_column(sa.Column("webhook_kinds", sa.Text(), nullable=True))
        batch.add_column(
            sa.Column("webhook_failures", sa.SmallInteger(), server_default="0", nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("webhook_failures")
        batch.drop_column("webhook_kinds")
        batch.drop_column("webhook_url")
