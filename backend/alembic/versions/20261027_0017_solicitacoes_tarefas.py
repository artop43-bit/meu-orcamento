"""v1.1: solicitações numeradas como tarefas e respostas a recados

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-27

As solicitações que já existem recebem números pela ordem em que foram criadas (#1, #2...).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("support_threads") as batch:
        batch.add_column(sa.Column("number", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("status_note", sa.String(length=200), nullable=True))
        batch.add_column(sa.Column("planned_version", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("announcement_id", sa.Uuid(), nullable=True))
        batch.alter_column("status", type_=sa.String(length=12), existing_type=sa.String(length=10))

    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id FROM support_threads ORDER BY created_at, id")
    ).fetchall()
    for number, (thread_id,) in enumerate(rows, start=1):
        conn.execute(
            sa.text("UPDATE support_threads SET number = :n WHERE id = :id"),
            {"n": number, "id": thread_id},
        )

    with op.batch_alter_table("support_threads") as batch:
        batch.alter_column("number", existing_type=sa.Integer(), nullable=False)
        batch.create_unique_constraint(op.f("uq_support_threads_number"), ["number"])
        batch.create_foreign_key(
            op.f("fk_support_threads_announcement_id_announcements"),
            "announcements",
            ["announcement_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index(op.f("ix_support_threads_announcement_id"), ["announcement_id"])


def downgrade() -> None:
    with op.batch_alter_table("support_threads") as batch:
        batch.drop_index(op.f("ix_support_threads_announcement_id"))
        batch.drop_constraint(
            op.f("fk_support_threads_announcement_id_announcements"), type_="foreignkey"
        )
        batch.drop_constraint(op.f("uq_support_threads_number"), type_="unique")
        batch.drop_column("announcement_id")
        batch.drop_column("planned_version")
        batch.drop_column("status_note")
        batch.drop_column("number")
    op.execute(
        "UPDATE support_threads SET status = 'open' WHERE status IN ('in_progress', 'planned')"
    )
    op.execute("UPDATE support_threads SET status = 'resolved' WHERE status = 'declined'")
    with op.batch_alter_table("support_threads") as batch:
        batch.alter_column("status", type_=sa.String(length=10), existing_type=sa.String(length=12))
