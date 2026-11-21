"""v1.10.1: solução de Mensageria (sessão WhatsApp Web, conversas e mensagens)

Revision ID: 0034
Revises: 0033
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "messaging_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("display_name", sa.String(length=120), nullable=True),
        sa.Column("qr_code", sa.Text(), nullable=True),
        sa.Column("bridge_token_hash", sa.String(length=64), nullable=True),
        sa.Column("bridge_token_prefix", sa.String(length=12), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_messaging_sessions_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_messaging_sessions"),
    )
    op.create_index("ix_messaging_sessions_user_id", "messaging_sessions", ["user_id"], unique=True)
    op.create_index(
        "ix_messaging_sessions_bridge_token_hash",
        "messaging_sessions",
        ["bridge_token_hash"],
        unique=False,
    )

    op.create_table(
        "messaging_chats",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("remote_jid", sa.String(length=64), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("notes", sa.String(length=300), nullable=True),
        sa.Column("budget_person", sa.String(length=80), nullable=True),
        sa.Column("unread_count", sa.Integer(), nullable=False),
        sa.Column("pinned", sa.Boolean(), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("last_message_preview", sa.String(length=240), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_messaging_chats_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_messaging_chats"),
        sa.UniqueConstraint("user_id", "remote_jid", name="uq_messaging_chats_user_jid"),
    )
    op.create_index("ix_messaging_chats_user_id", "messaging_chats", ["user_id"], unique=False)
    op.create_index(
        "ix_messaging_chats_user_last",
        "messaging_chats",
        ["user_id", "last_message_at"],
        unique=False,
    )

    op.create_table(
        "messaging_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("chat_id", sa.Uuid(), nullable=False),
        sa.Column("direction", sa.String(length=4), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("message_type", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("external_id", sa.String(length=160), nullable=True),
        sa.Column("reply_to_id", sa.Uuid(), nullable=True),
        sa.Column("error_detail", sa.String(length=300), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["chat_id"],
            ["messaging_chats.id"],
            name="fk_messaging_messages_chat_id_messaging_chats",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reply_to_id"],
            ["messaging_messages.id"],
            name="fk_messaging_messages_reply_to_id_messaging_messages",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_messaging_messages_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_messaging_messages"),
    )
    op.create_index(
        "ix_messaging_messages_user_id", "messaging_messages", ["user_id"], unique=False
    )
    op.create_index(
        "ix_messaging_messages_chat_id", "messaging_messages", ["chat_id"], unique=False
    )
    op.create_index(
        "ix_messaging_messages_reply_to_id", "messaging_messages", ["reply_to_id"], unique=False
    )
    op.create_index(
        "ix_messaging_messages_chat_created",
        "messaging_messages",
        ["chat_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_messaging_messages_user_status",
        "messaging_messages",
        ["user_id", "direction", "status"],
        unique=False,
    )
    op.create_index(
        "ix_messaging_messages_user_external",
        "messaging_messages",
        ["user_id", "external_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_messaging_messages_user_external", table_name="messaging_messages")
    op.drop_index("ix_messaging_messages_user_status", table_name="messaging_messages")
    op.drop_index("ix_messaging_messages_chat_created", table_name="messaging_messages")
    op.drop_index("ix_messaging_messages_reply_to_id", table_name="messaging_messages")
    op.drop_index("ix_messaging_messages_chat_id", table_name="messaging_messages")
    op.drop_index("ix_messaging_messages_user_id", table_name="messaging_messages")
    op.drop_table("messaging_messages")

    op.drop_index("ix_messaging_chats_user_last", table_name="messaging_chats")
    op.drop_index("ix_messaging_chats_user_id", table_name="messaging_chats")
    op.drop_table("messaging_chats")

    op.drop_index("ix_messaging_sessions_bridge_token_hash", table_name="messaging_sessions")
    op.drop_index("ix_messaging_sessions_user_id", table_name="messaging_sessions")
    op.drop_table("messaging_sessions")
