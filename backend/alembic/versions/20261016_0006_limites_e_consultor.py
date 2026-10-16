"""limites por categoria e convite do 2fa

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-16

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("categories") as batch:
        batch.add_column(sa.Column("monthly_limit", sa.Numeric(12, 2), nullable=True))
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column("twofa_prompt_dismissed_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("twofa_prompt_dismissed_at")
    with op.batch_alter_table("categories") as batch:
        batch.drop_column("monthly_limit")
