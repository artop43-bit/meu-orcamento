"""v1.10.1: Mensageria com recursos de CRM (etiquetas, status, follow-up e respostas rápidas)

Revision ID: 0038
Revises: 0037
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0038"
down_revision: str | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("messaging_chats") as batch_op:
        batch_op.add_column(sa.Column("tags", sa.String(length=240), nullable=True))
        batch_op.add_column(
            sa.Column(
                "service_status",
                sa.String(length=20),
                server_default="open",
                nullable=False,
            )
        )
        batch_op.add_column(sa.Column("followup_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("followup_note", sa.String(length=200), nullable=True))

    op.create_table(
        "messaging_quick_replies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("shortcut", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=80), nullable=False),
        sa.Column("body", sa.String(length=2000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_messaging_quick_replies_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_messaging_quick_replies"),
        sa.UniqueConstraint(
            "user_id",
            "shortcut",
            name="uq_messaging_quick_replies_user_shortcut",
        ),
    )
    op.create_index(
        "ix_messaging_quick_replies_user_id",
        "messaging_quick_replies",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_messaging_quick_replies_user_id",
        table_name="messaging_quick_replies",
    )
    op.drop_table("messaging_quick_replies")

    with op.batch_alter_table("messaging_chats") as batch_op:
        batch_op.drop_column("followup_note")
        batch_op.drop_column("followup_at")
        batch_op.drop_column("service_status")
        batch_op.drop_column("tags")
