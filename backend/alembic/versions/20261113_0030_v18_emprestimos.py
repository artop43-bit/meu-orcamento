"""v1.8: empréstimos a amigos com juros e parcelas (Divisões)

Revision ID: 0030
Revises: 0029
Create Date: 2026-11-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "personal_loans",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("person", sa.String(length=60), nullable=False),
        sa.Column("description", sa.String(length=120), nullable=True),
        sa.Column("direction", sa.String(length=7), nullable=False),
        sa.Column("principal", sa.Numeric(12, 2), nullable=False),
        sa.Column("mode", sa.String(length=6), nullable=False),
        sa.Column("rate", sa.Numeric(8, 4), nullable=False),
        sa.Column("frequency", sa.String(length=6), nullable=False),
        sa.Column("count", sa.SmallInteger(), nullable=False),
        sa.Column("first_due", sa.Date(), nullable=False),
        sa.Column("late_fee", sa.Numeric(8, 4), nullable=True),
        sa.Column("late_interest", sa.Numeric(8, 4), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_personal_loans_user_id", "personal_loans", ["user_id"])
    op.create_table(
        "loan_installments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "loan_id",
            sa.Uuid(),
            sa.ForeignKey("personal_loans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("number", sa.SmallInteger(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("interest", sa.Numeric(12, 2), nullable=False),
        sa.Column("principal_part", sa.Numeric(12, 2), nullable=False),
        sa.Column("received_at", sa.Date(), nullable=True),
        sa.Column("received_amount", sa.Numeric(12, 2), nullable=True),
        sa.UniqueConstraint("loan_id", "number"),
    )
    op.create_index("ix_loan_installments_loan_id", "loan_installments", ["loan_id"])
    for table in ("incomes", "expenses"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("personal_loan_id", sa.Uuid(), nullable=True))
            batch.create_foreign_key(
                f"fk_{table}_personal_loan_id_personal_loans",
                "personal_loans",
                ["personal_loan_id"],
                ["id"],
                ondelete="CASCADE",
            )
            batch.create_index(f"ix_{table}_personal_loan_id", ["personal_loan_id"])


def downgrade() -> None:
    for table in ("incomes", "expenses"):
        with op.batch_alter_table(table) as batch:
            batch.drop_index(f"ix_{table}_personal_loan_id")
            batch.drop_constraint(f"fk_{table}_personal_loan_id_personal_loans", type_="foreignkey")
            batch.drop_column("personal_loan_id")
    op.drop_index("ix_loan_installments_loan_id", table_name="loan_installments")
    op.drop_table("loan_installments")
    op.drop_index("ix_personal_loans_user_id", table_name="personal_loans")
    op.drop_table("personal_loans")
