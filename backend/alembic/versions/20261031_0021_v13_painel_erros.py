"""v1.3: painel do Orçamento personalizado e painel de erros

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("dashboard", sa.String(length=600), nullable=True))
    op.create_table(
        "error_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("fingerprint", sa.String(length=32), nullable=False, unique=True),
        sa.Column("source", sa.String(length=6), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("message", sa.String(length=300), nullable=False),
        sa.Column("path", sa.String(length=200), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("user_agent", sa.String(length=200), nullable=True),
        sa.Column("release", sa.String(length=20), nullable=True),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_error_events_last_seen", "error_events", ["last_seen"])


def downgrade() -> None:
    op.drop_index("ix_error_events_last_seen", table_name="error_events")
    op.drop_table("error_events")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("dashboard")
