"""v1.4: link secreto de calendário (vencimentos na agenda)

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("calendar_token", sa.String(length=64), nullable=True))
        batch.create_unique_constraint("uq_users_calendar_token", ["calendar_token"])


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("uq_users_calendar_token", type_="unique")
        batch.drop_column("calendar_token")
