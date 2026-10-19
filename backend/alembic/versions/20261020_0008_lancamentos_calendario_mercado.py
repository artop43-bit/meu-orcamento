"""lancamentos flexiveis, calendario e mercado

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("recurring_items") as batch:
        batch.add_column(
            sa.Column("interval_months", sa.SmallInteger(), nullable=False, server_default="1")
        )
        batch.add_column(sa.Column("income_type", sa.String(length=10), nullable=True))
        batch.add_column(sa.Column("payment_method", sa.String(length=12), nullable=True))
        batch.add_column(sa.Column("notes", sa.String(length=500), nullable=True))
    with op.batch_alter_table("incomes") as batch:
        batch.add_column(
            sa.Column("income_type", sa.String(length=10), nullable=False, server_default="fixed")
        )
        batch.add_column(sa.Column("day", sa.SmallInteger(), nullable=True))
        batch.add_column(sa.Column("notes", sa.String(length=500), nullable=True))
    with op.batch_alter_table("expenses") as batch:
        batch.add_column(sa.Column("payment_method", sa.String(length=12), nullable=True))
    with op.batch_alter_table("investments") as batch:
        batch.add_column(sa.Column("ticker", sa.String(length=12), nullable=True))
        batch.add_column(sa.Column("quantity", sa.Numeric(18, 6), nullable=True))

    op.create_table(
        "planned_expenses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("description", sa.String(length=120), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=True),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("expense_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_planned_expenses_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name=op.f("fk_planned_expenses_category_id_categories"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["expense_id"],
            ["expenses.id"],
            name=op.f("fk_planned_expenses_expense_id_expenses"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_planned_expenses")),
    )
    op.create_index(op.f("ix_planned_expenses_user_id"), "planned_expenses", ["user_id"])
    op.create_index(op.f("ix_planned_expenses_date"), "planned_expenses", ["date"])

    op.create_table(
        "watch_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_watch_items_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_watch_items")),
        sa.UniqueConstraint("user_id", "symbol", name=op.f("uq_watch_items_user_id")),
    )
    op.create_index(op.f("ix_watch_items_user_id"), "watch_items", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_watch_items_user_id"), table_name="watch_items")
    op.drop_table("watch_items")
    op.drop_index(op.f("ix_planned_expenses_date"), table_name="planned_expenses")
    op.drop_index(op.f("ix_planned_expenses_user_id"), table_name="planned_expenses")
    op.drop_table("planned_expenses")
    with op.batch_alter_table("investments") as batch:
        batch.drop_column("quantity")
        batch.drop_column("ticker")
    with op.batch_alter_table("expenses") as batch:
        batch.drop_column("payment_method")
    with op.batch_alter_table("incomes") as batch:
        batch.drop_column("notes")
        batch.drop_column("day")
        batch.drop_column("income_type")
    with op.batch_alter_table("recurring_items") as batch:
        batch.drop_column("notes")
        batch.drop_column("payment_method")
        batch.drop_column("income_type")
        batch.drop_column("interval_months")
