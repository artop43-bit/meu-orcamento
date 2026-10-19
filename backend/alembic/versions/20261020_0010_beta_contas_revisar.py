"""v0.7: aprovacao do beta, log de e-mails, contas e saldos, revisar e novas categorias

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-20

"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_CATEGORIES = [("Compras", "#ff9da7"), ("Assinaturas", "#8cd17d"), ("Pets", "#d4a6c8")]


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column(
                "access_status", sa.String(length=10), nullable=False, server_default="approved"
            )
        )
        batch.add_column(sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="0"))

    op.create_table(
        "email_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("to", sa.String(length=320), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_log")),
    )
    op.create_index(op.f("ix_email_log_to"), "email_log", ["to"])
    op.create_index(op.f("ix_email_log_created_at"), "email_log", ["created_at"])

    op.create_table(
        "money_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("initial_balance", sa.Numeric(14, 2), nullable=False),
        sa.Column("color", sa.String(length=7), nullable=True),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_money_accounts_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_money_accounts")),
    )
    op.create_index(op.f("ix_money_accounts_user_id"), "money_accounts", ["user_id"])

    op.create_table(
        "transfers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("from_account_id", sa.Uuid(), nullable=False),
        sa.Column("to_account_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("notes", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_transfers_user_id_users"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["from_account_id"],
            ["money_accounts.id"],
            name=op.f("fk_transfers_from_account_id_money_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["to_account_id"],
            ["money_accounts.id"],
            name=op.f("fk_transfers_to_account_id_money_accounts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transfers")),
    )
    op.create_index(op.f("ix_transfers_user_id"), "transfers", ["user_id"])

    with op.batch_alter_table("expenses") as batch:
        batch.add_column(sa.Column("account_id", sa.Uuid(), nullable=True))
        batch.add_column(
            sa.Column("needs_review", sa.Boolean(), nullable=False, server_default="0")
        )
        batch.create_foreign_key(
            op.f("fk_expenses_account_id_money_accounts"),
            "money_accounts",
            ["account_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index(op.f("ix_expenses_account_id"), ["account_id"])
    with op.batch_alter_table("incomes") as batch:
        batch.add_column(sa.Column("account_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            op.f("fk_incomes_account_id_money_accounts"),
            "money_accounts",
            ["account_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index(op.f("ix_incomes_account_id"), ["account_id"])
    with op.batch_alter_table("credit_cards") as batch:
        batch.add_column(sa.Column("account_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            op.f("fk_credit_cards_account_id_money_accounts"),
            "money_accounts",
            ["account_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # Categorias padrão novas também para quem já tem conta (se ainda não tiver uma com o nome).
    conn = op.get_bind()
    users = [row[0] for row in conn.execute(sa.text("SELECT id FROM users"))]
    categories = sa.table(
        "categories",
        sa.column("id", sa.Uuid()),
        sa.column("user_id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("is_essential", sa.Boolean()),
        sa.column("color", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    has_created_at = "created_at" in {c["name"] for c in sa.inspect(conn).get_columns("categories")}
    now = datetime.now(UTC)
    for user_id in users:
        existing = {
            row[0].lower()
            for row in conn.execute(
                sa.text("SELECT name FROM categories WHERE user_id = :u"), {"u": user_id}
            )
        }
        for name, color in NEW_CATEGORIES:
            if name.lower() in existing:
                continue
            values = {
                "id": uuid.uuid4(),
                "user_id": user_id if not isinstance(user_id, str) else uuid.UUID(user_id),
                "name": name,
                "is_essential": False,
                "color": color,
            }
            if has_created_at:
                values["created_at"] = now
            op.execute(categories.insert().values(**values))


def downgrade() -> None:
    with op.batch_alter_table("credit_cards") as batch:
        batch.drop_constraint(op.f("fk_credit_cards_account_id_money_accounts"), type_="foreignkey")
        batch.drop_column("account_id")
    with op.batch_alter_table("incomes") as batch:
        batch.drop_index(op.f("ix_incomes_account_id"))
        batch.drop_constraint(op.f("fk_incomes_account_id_money_accounts"), type_="foreignkey")
        batch.drop_column("account_id")
    with op.batch_alter_table("expenses") as batch:
        batch.drop_index(op.f("ix_expenses_account_id"))
        batch.drop_constraint(op.f("fk_expenses_account_id_money_accounts"), type_="foreignkey")
        batch.drop_column("needs_review")
        batch.drop_column("account_id")
    op.drop_index(op.f("ix_transfers_user_id"), table_name="transfers")
    op.drop_table("transfers")
    op.drop_index(op.f("ix_money_accounts_user_id"), table_name="money_accounts")
    op.drop_table("money_accounts")
    op.drop_index(op.f("ix_email_log_created_at"), table_name="email_log")
    op.drop_index(op.f("ix_email_log_to"), table_name="email_log")
    op.drop_table("email_log")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("is_admin")
        batch.drop_column("approved_at")
        batch.drop_column("access_status")
