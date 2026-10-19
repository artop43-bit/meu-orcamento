"""v0.7.5: solicitações em conversa, imagens, perfil e cartão de débito

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-21

O feedback antigo (uma mensagem só, sem resposta) vira solicitação: cada item passa a ser uma
conversa com a mensagem original. A tabela "feedback" deixa de existir.
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _title(message: str) -> str:
    first = (message or "").strip().split("\n", 1)[0].strip()[:80]
    return first if len(first) >= 3 else "Feedback"


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("display_name", sa.String(length=60), nullable=True))
        batch.add_column(sa.Column("bio", sa.String(length=160), nullable=True))
        batch.add_column(sa.Column("city", sa.String(length=80), nullable=True))
        batch.add_column(sa.Column("profession", sa.String(length=80), nullable=True))
        batch.add_column(sa.Column("profile_prefs", sa.Text(), nullable=True))

    with op.batch_alter_table("credit_cards") as batch:
        batch.add_column(
            sa.Column("kind", sa.String(length=6), nullable=False, server_default="credit")
        )
        batch.alter_column("closing_day", existing_type=sa.SmallInteger(), nullable=True)
        batch.alter_column("due_day", existing_type=sa.SmallInteger(), nullable=True)

    with op.batch_alter_table("expenses") as batch:
        batch.add_column(sa.Column("debit_card_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            op.f("fk_expenses_debit_card_id_credit_cards"),
            "credit_cards",
            ["debit_card_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.create_table(
        "support_threads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("user_unread", sa.Boolean(), nullable=False),
        sa.Column("admin_unread", sa.Boolean(), nullable=False),
        sa.Column("page", sa.String(length=200), nullable=True),
        sa.Column("app_version", sa.String(length=20), nullable=True),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_support_threads_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_support_threads")),
    )
    op.create_index(op.f("ix_support_threads_user_id"), "support_threads", ["user_id"])
    op.create_index(
        "ix_support_threads_last_message_at", "support_threads", ["last_message_at"]
    )

    op.create_table(
        "support_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("thread_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=True),
        sa.Column("from_admin", sa.Boolean(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["thread_id"],
            ["support_threads.id"],
            name=op.f("fk_support_messages_thread_id_support_threads"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name=op.f("fk_support_messages_author_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_support_messages")),
    )
    op.create_index(op.f("ix_support_messages_thread_id"), "support_messages", ["thread_id"])

    op.create_table(
        "stored_files",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(length=12), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("content_type", sa.String(length=20), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_stored_files_owner_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["support_messages.id"],
            name=op.f("fk_stored_files_message_id_support_messages"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stored_files")),
    )
    op.create_index(op.f("ix_stored_files_message_id"), "stored_files", ["message_id"])
    op.create_index("ix_stored_files_owner_purpose", "stored_files", ["owner_id", "purpose"])

    # Feedback antigo → solicitações (só os que ainda têm dono).
    conn = op.get_bind()
    threads = sa.table(
        "support_threads",
        *(
            sa.column(name, kind)
            for name, kind in (
                ("id", sa.Uuid()),
                ("user_id", sa.Uuid()),
                ("title", sa.String()),
                ("kind", sa.String()),
                ("status", sa.String()),
                ("user_unread", sa.Boolean()),
                ("admin_unread", sa.Boolean()),
                ("page", sa.String()),
                ("app_version", sa.String()),
                ("user_agent", sa.String()),
                ("created_at", sa.DateTime(timezone=True)),
                ("last_message_at", sa.DateTime(timezone=True)),
            )
        ),
    )
    messages = sa.table(
        "support_messages",
        sa.column("id", sa.Uuid()),
        sa.column("thread_id", sa.Uuid()),
        sa.column("author_id", sa.Uuid()),
        sa.column("from_admin", sa.Boolean()),
        sa.column("body", sa.Text()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    old_feedback = sa.table(
        "feedback",
        sa.column("user_id", sa.Uuid()),
        sa.column("kind", sa.String()),
        sa.column("message", sa.Text()),
        sa.column("page", sa.String()),
        sa.column("user_agent", sa.String()),
        sa.column("app_version", sa.String()),
        sa.column("status", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    old = conn.execute(
        sa.select(
            old_feedback.c.user_id,
            old_feedback.c.kind,
            old_feedback.c.message,
            old_feedback.c.page,
            old_feedback.c.user_agent,
            old_feedback.c.app_version,
            old_feedback.c.status,
            old_feedback.c.created_at,
        ).where(old_feedback.c.user_id.is_not(None))
    ).all()
    for user_id, kind, message, page, user_agent, app_version, status, created_at in old:
        thread_id = uuid.uuid4()
        conn.execute(
            threads.insert().values(
                id=thread_id,
                user_id=user_id,
                title=_title(message),
                kind=kind if kind in ("idea", "bug", "other") else "other",
                status="resolved" if status == "done" else "open",
                user_unread=False,
                admin_unread=status == "new",
                page=page,
                app_version=app_version,
                user_agent=user_agent,
                created_at=created_at,
                last_message_at=created_at,
            )
        )
        conn.execute(
            messages.insert().values(
                id=uuid.uuid4(),
                thread_id=thread_id,
                author_id=user_id,
                from_admin=False,
                body=message,
                created_at=created_at,
            )
        )

    op.drop_index(op.f("ix_feedback_user_id"), table_name="feedback")
    op.drop_table("feedback")


def downgrade() -> None:
    op.create_table(
        "feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("page", sa.String(length=200), nullable=True),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        sa.Column("app_version", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_feedback_user_id_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_feedback")),
    )
    op.create_index(op.f("ix_feedback_user_id"), "feedback", ["user_id"])
    # Volta só a primeira mensagem de cada solicitação (as respostas não existiam antes).
    conn = op.get_bind()
    t = sa.table(
        "support_threads",
        sa.column("id", sa.Uuid()),
        sa.column("user_id", sa.Uuid()),
        sa.column("kind", sa.String()),
        sa.column("page", sa.String()),
        sa.column("user_agent", sa.String()),
        sa.column("app_version", sa.String()),
        sa.column("status", sa.String()),
        sa.column("admin_unread", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    m = sa.table(
        "support_messages",
        sa.column("thread_id", sa.Uuid()),
        sa.column("from_admin", sa.Boolean()),
        sa.column("body", sa.Text()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    first = (
        sa.select(sa.func.min(m.c.created_at))
        .where(m.c.thread_id == t.c.id)
        .correlate(t)
        .scalar_subquery()
    )
    rows = conn.execute(
        sa.select(
            t.c.user_id,
            t.c.kind,
            m.c.body,
            t.c.page,
            t.c.user_agent,
            t.c.app_version,
            t.c.status,
            t.c.admin_unread,
            t.c.created_at,
        )
        .join_from(t, m, m.c.thread_id == t.c.id)
        .where(m.c.from_admin.is_(False), m.c.created_at == first)
    ).all()
    feedback = sa.table(
        "feedback",
        *(
            sa.column(name, kind)
            for name, kind in (
                ("id", sa.Uuid()),
                ("user_id", sa.Uuid()),
                ("kind", sa.String()),
                ("message", sa.Text()),
                ("page", sa.String()),
                ("user_agent", sa.String()),
                ("app_version", sa.String()),
                ("status", sa.String()),
                ("created_at", sa.DateTime(timezone=True)),
            )
        ),
    )
    for user_id, kind, body, page, agent, version, status, unread, created in rows:
        conn.execute(
            feedback.insert().values(
                id=uuid.uuid4(),
                user_id=user_id,
                kind=kind,
                message=body,
                page=page,
                user_agent=agent,
                app_version=version,
                status="done" if status == "resolved" else ("new" if unread else "read"),
                created_at=created,
            )
        )

    op.drop_index("ix_stored_files_owner_purpose", table_name="stored_files")
    op.drop_index(op.f("ix_stored_files_message_id"), table_name="stored_files")
    op.drop_table("stored_files")
    op.drop_index(op.f("ix_support_messages_thread_id"), table_name="support_messages")
    op.drop_table("support_messages")
    op.drop_index("ix_support_threads_last_message_at", table_name="support_threads")
    op.drop_index(op.f("ix_support_threads_user_id"), table_name="support_threads")
    op.drop_table("support_threads")

    with op.batch_alter_table("expenses") as batch:
        batch.drop_constraint(op.f("fk_expenses_debit_card_id_credit_cards"), type_="foreignkey")
        batch.drop_column("debit_card_id")
    # Cartões só de débito não cabem no modelo antigo (fechamento e vencimento obrigatórios).
    conn.execute(sa.text("DELETE FROM credit_cards WHERE kind = 'debit'"))
    with op.batch_alter_table("credit_cards") as batch:
        batch.alter_column("due_day", existing_type=sa.SmallInteger(), nullable=False)
        batch.alter_column("closing_day", existing_type=sa.SmallInteger(), nullable=False)
        batch.drop_column("kind")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("profile_prefs")
        batch.drop_column("profession")
        batch.drop_column("city")
        batch.drop_column("bio")
        batch.drop_column("display_name")
