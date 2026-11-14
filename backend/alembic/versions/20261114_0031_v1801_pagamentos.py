"""v1.8.0.1: histórico de pagamentos dos empréstimos a amigos, telefone e parcelas refeitas

Revision ID: 0031
Revises: 0030
Create Date: 2026-11-14
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("personal_loans") as batch:
        batch.add_column(sa.Column("phone", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("rescheduled_at", sa.DateTime(timezone=True), nullable=True))
    payments = op.create_table(
        "loan_payments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "loan_id",
            sa.Uuid(),
            sa.ForeignKey("personal_loans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("paid_on", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("mode", sa.String(length=7), nullable=False),
        sa.Column("discount", sa.Numeric(12, 2), nullable=False),
        sa.Column("allocation", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_loan_payments_loan_id", "loan_payments", ["loan_id"])
    # O que já foi recebido na v1.8.0 vira um pagamento por parcela (para aparecer no histórico
    # e poder ser desfeito).
    rows = op.get_bind().execute(
        sa.text(
            "SELECT loan_id, number, received_amount, received_at FROM loan_installments "
            "WHERE received_amount IS NOT NULL AND received_at IS NOT NULL ORDER BY number"
        )
    )
    now = datetime.now(UTC)
    values = [
        {
            "id": uuid.uuid4(),
            "loan_id": loan_id if isinstance(loan_id, uuid.UUID) else uuid.UUID(str(loan_id)),
            "paid_on": received_at,
            "amount": amount,
            "mode": "next",
            "discount": 0,
            "allocation": [[number, str(amount), "0"]],
            "created_at": now,
        }
        for loan_id, number, amount, received_at in rows
    ]
    if values:
        op.bulk_insert(payments, values)


def downgrade() -> None:
    op.drop_index("ix_loan_payments_loan_id", table_name="loan_payments")
    op.drop_table("loan_payments")
    with op.batch_alter_table("personal_loans") as batch:
        batch.drop_column("rescheduled_at")
        batch.drop_column("phone")
