"""v1.7.5: histórico do Tire sua dúvida (conversas guardadas por 30 dias)

Revision ID: 0029
Revises: 0028
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("ask_history", sa.Boolean(), nullable=False, server_default="1"))
    op.create_table(
        "ask_conversations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_ask_conversations_user_id_updated_at", "ask_conversations", ["user_id", "updated_at"]
    )
    op.create_table(
        "ask_messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            sa.ForeignKey("ask_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("question", sa.String(length=200), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ask_messages_conversation_id", "ask_messages", ["conversation_id"])


def downgrade() -> None:
    op.drop_index("ix_ask_messages_conversation_id", table_name="ask_messages")
    op.drop_table("ask_messages")
    op.drop_index("ix_ask_conversations_user_id_updated_at", table_name="ask_conversations")
    op.drop_table("ask_conversations")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("ask_history")
