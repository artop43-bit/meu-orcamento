"""v1.10.1: Governança de acesso, bloqueio de recursos e cota de armazenamento por usuário

Revision ID: 0040
Revises: 0039
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0040"
down_revision: str | None = "0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("blocked_resources", sa.Text(), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "storage_quota_mb",
            sa.SmallInteger(),
            nullable=False,
            server_default="50",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "storage_quota_mb")
    op.drop_column("users", "blocked_resources")
