"""CRM: remove opções de sincronização automática sem agendador.

Revision ID: 0039
Revises: 0038
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0039"
down_revision: str | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("data_sources") as batch:
        batch.drop_column("refresh_interval_minutes")
        batch.drop_column("sync_failures")


def downgrade() -> None:
    with op.batch_alter_table("data_sources") as batch:
        batch.add_column(sa.Column("refresh_interval_minutes", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column("sync_failures", sa.SmallInteger(), nullable=False, server_default="0")
        )
