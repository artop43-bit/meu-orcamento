"""v1.3.1: respostas públicas nos recados, tema das solicitações e anexos de documentos

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-01

As respostas a recados que viraram conversas privadas (v1.1 a v1.3) passam para a thread
pública do recado, marcadas como "migradas" (a pessoa é avisada na tela). As conversas
antigas são removidas depois de copiadas.
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "announcement_replies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "announcement_id",
            sa.Uuid(),
            sa.ForeignKey("announcements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "author_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("from_admin", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("migrated", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_announcement_replies_announcement",
        "announcement_replies",
        ["announcement_id", "created_at"],
    )
    with op.batch_alter_table("stored_files") as batch:
        batch.alter_column(
            "content_type", type_=sa.String(length=100), existing_type=sa.String(length=20)
        )
        batch.add_column(sa.Column("filename", sa.String(length=120), nullable=True))

    conn = op.get_bind()
    threads = conn.execute(
        sa.text("SELECT id, announcement_id FROM support_threads WHERE announcement_id IS NOT NULL")
    ).fetchall()
    for thread_id, announcement_id in threads:
        messages = conn.execute(
            sa.text(
                "SELECT author_id, from_admin, body, created_at FROM support_messages "
                "WHERE thread_id = :t AND author_id IS NOT NULL ORDER BY created_at"
            ),
            {"t": thread_id},
        ).fetchall()
        for author_id, from_admin, body, created_at in messages:
            conn.execute(
                sa.text(
                    "INSERT INTO announcement_replies "
                    "(id, announcement_id, author_id, from_admin, body, migrated, created_at) "
                    "VALUES (:id, :a, :u, :f, :b, :m, :c)"
                ),
                {
                    "id": uuid.uuid4() if conn.dialect.name == "postgresql" else uuid.uuid4().hex,
                    "a": announcement_id,
                    "u": author_id,
                    "f": from_admin,
                    "b": body,
                    "m": True,
                    "c": created_at,
                },
            )
        conn.execute(sa.text("DELETE FROM inbox_items WHERE thread_id = :t"), {"t": thread_id})
        conn.execute(
            sa.text(
                "DELETE FROM stored_files WHERE message_id IN "
                "(SELECT id FROM support_messages WHERE thread_id = :t)"
            ),
            {"t": thread_id},
        )
        conn.execute(sa.text("DELETE FROM support_messages WHERE thread_id = :t"), {"t": thread_id})
        conn.execute(sa.text("DELETE FROM support_threads WHERE id = :t"), {"t": thread_id})


def downgrade() -> None:
    with op.batch_alter_table("stored_files") as batch:
        batch.drop_column("filename")
        batch.alter_column(
            "content_type", type_=sa.String(length=20), existing_type=sa.String(length=100)
        )
    op.drop_index("ix_announcement_replies_announcement", table_name="announcement_replies")
    op.drop_table("announcement_replies")
