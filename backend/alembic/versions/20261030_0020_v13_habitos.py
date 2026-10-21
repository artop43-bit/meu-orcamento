"""v1.3: desafios de economia e resumo semanal

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "challenges",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("title", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column(
            "category_id",
            sa.Uuid(),
            sa.ForeignKey("categories.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("keywords", sa.String(length=200), nullable=True),
        sa.Column("max_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("days", sa.SmallInteger(), nullable=False),
        sa.Column("result", sa.String(length=6), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_challenges_user_id", "challenges", ["user_id"])
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column("notify_weekly", sa.Boolean(), nullable=False, server_default="1")
        )
        batch.add_column(sa.Column("push_weekly", sa.Boolean(), nullable=False, server_default="1"))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("push_weekly")
        batch.drop_column("notify_weekly")
    op.drop_index("ix_challenges_user_id", table_name="challenges")
    op.drop_table("challenges")
