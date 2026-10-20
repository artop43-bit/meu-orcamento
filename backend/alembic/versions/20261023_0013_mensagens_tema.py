"""v0.9: caixa de mensagens, recados da administração e aparência salva na conta

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column("notify_messages", sa.Boolean(), nullable=False, server_default="1")
        )
        batch.add_column(sa.Column("theme", sa.String(length=6), nullable=True))
        batch.add_column(sa.Column("accent", sa.String(length=8), nullable=True))

    op.create_table(
        "announcements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("important", sa.Boolean(), nullable=False),
        sa.Column("include_pending", sa.Boolean(), nullable=False),
        sa.Column("recipients", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name=op.f("fk_announcements_author_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_announcements")),
    )

    op.create_table(
        "inbox_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("important", sa.Boolean(), nullable=False),
        sa.Column("thread_id", sa.Uuid(), nullable=True),
        sa.Column("announcement_id", sa.Uuid(), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_inbox_items_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["thread_id"],
            ["support_threads.id"],
            name=op.f("fk_inbox_items_thread_id_support_threads"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["announcement_id"],
            ["announcements.id"],
            name=op.f("fk_inbox_items_announcement_id_announcements"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inbox_items")),
    )
    op.create_index("ix_inbox_items_user_created", "inbox_items", ["user_id", "created_at"])
    op.create_index(op.f("ix_inbox_items_thread_id"), "inbox_items", ["thread_id"])
    op.create_index(op.f("ix_inbox_items_announcement_id"), "inbox_items", ["announcement_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_inbox_items_announcement_id"), table_name="inbox_items")
    op.drop_index(op.f("ix_inbox_items_thread_id"), table_name="inbox_items")
    op.drop_index("ix_inbox_items_user_created", table_name="inbox_items")
    op.drop_table("inbox_items")
    op.drop_table("announcements")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("accent")
        batch.drop_column("theme")
        batch.drop_column("notify_messages")
