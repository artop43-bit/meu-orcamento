"""v1.0: mês financeiro pelo dia do salário, alertas e divisão de despesas

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column("month_start_day", sa.SmallInteger(), nullable=False, server_default="1")
        )
        batch.add_column(
            sa.Column("notify_alerts", sa.Boolean(), nullable=False, server_default="1")
        )

    op.create_table(
        "split_shares",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("expense_id", sa.Uuid(), nullable=True),
        sa.Column("person", sa.String(length=60), nullable=False),
        sa.Column("description", sa.String(length=120), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("direction", sa.String(length=7), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_split_shares_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["expense_id"],
            ["expenses.id"],
            name=op.f("fk_split_shares_expense_id_expenses"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_split_shares")),
    )
    op.create_index(op.f("ix_split_shares_user_id"), "split_shares", ["user_id"])
    op.create_index(op.f("ix_split_shares_expense_id"), "split_shares", ["expense_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_split_shares_expense_id"), table_name="split_shares")
    op.drop_index(op.f("ix_split_shares_user_id"), table_name="split_shares")
    op.drop_table("split_shares")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("notify_alerts")
        batch.drop_column("month_start_day")
