"""v1.0: financiamentos e empréstimos, outras dívidas e patrimônio mês a mês

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MONEY = sa.Numeric(12, 2)


def _user_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["user_id"], ["users.id"], name=op.f(f"fk_{table}_user_id_users"), ondelete="CASCADE"
    )


def upgrade() -> None:
    op.create_table(
        "loans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("institution", sa.String(length=80), nullable=True),
        sa.Column("principal", MONEY, nullable=False),
        sa.Column("rate", sa.Numeric(8, 4), nullable=False),
        sa.Column("rate_period", sa.String(length=7), nullable=False),
        sa.Column("system", sa.String(length=5), nullable=False),
        sa.Column("installments", sa.SmallInteger(), nullable=False),
        sa.Column("first_due", sa.Date(), nullable=False),
        sa.Column("paid_before", sa.SmallInteger(), nullable=False),
        sa.Column("insurance_monthly", MONEY, nullable=False),
        sa.Column("fee_monthly", MONEY, nullable=False),
        sa.Column("iof", MONEY, nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=True),
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        _user_fk("loans"),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name=op.f("fk_loans_category_id_categories"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["money_accounts.id"],
            name=op.f("fk_loans_account_id_money_accounts"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_loans")),
    )
    op.create_index(op.f("ix_loans_user_id"), "loans", ["user_id"])

    op.create_table(
        "other_debts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("balance", MONEY, nullable=False),
        sa.Column("monthly_payment", MONEY, nullable=True),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        _user_fk("other_debts"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_other_debts")),
    )
    op.create_index(op.f("ix_other_debts_user_id"), "other_debts", ["user_id"])

    op.create_table(
        "net_worth_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("assets", MONEY, nullable=False),
        sa.Column("debts", MONEY, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        _user_fk("net_worth_snapshots"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_net_worth_snapshots")),
        sa.UniqueConstraint("user_id", "month", name=op.f("uq_net_worth_snapshots_user_id")),
    )
    op.create_index(op.f("ix_net_worth_snapshots_user_id"), "net_worth_snapshots", ["user_id"])

    with op.batch_alter_table("expenses") as batch:
        batch.add_column(sa.Column("loan_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            op.f("fk_expenses_loan_id_loans"), "loans", ["loan_id"], ["id"], ondelete="SET NULL"
        )
        batch.create_index(op.f("ix_expenses_loan_id"), ["loan_id"])


def downgrade() -> None:
    with op.batch_alter_table("expenses") as batch:
        batch.drop_index(op.f("ix_expenses_loan_id"))
        batch.drop_constraint(op.f("fk_expenses_loan_id_loans"), type_="foreignkey")
        batch.drop_column("loan_id")
    op.drop_index(op.f("ix_net_worth_snapshots_user_id"), table_name="net_worth_snapshots")
    op.drop_table("net_worth_snapshots")
    op.drop_index(op.f("ix_other_debts_user_id"), table_name="other_debts")
    op.drop_table("other_debts")
    op.drop_index(op.f("ix_loans_user_id"), table_name="loans")
    op.drop_table("loans")
