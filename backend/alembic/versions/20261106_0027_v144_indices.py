"""v1.4.4: índices nas chaves estrangeiras que ainda não tinham

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-06
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (tabela, coluna) — os mesmos de app/models/indexes.py.
INDEXES = [
    ("money_accounts", "benefit_category_id"),
    ("money_accounts", "recurring_id"),
    ("recurring_items", "category_id"),
    ("recurring_items", "account_id"),
    ("announcements", "author_id"),
    ("credit_cards", "account_id"),
    ("transfers", "from_account_id"),
    ("transfers", "to_account_id"),
    ("announcement_replies", "author_id"),
    ("category_rules", "category_id"),
    ("challenges", "category_id"),
    ("loans", "account_id"),
    ("loans", "category_id"),
    ("expenses", "category_id"),
    ("expenses", "debit_card_id"),
    ("support_messages", "author_id"),
    ("planned_expenses", "category_id"),
    ("planned_expenses", "expense_id"),
]


def upgrade() -> None:
    for table, column in INDEXES:
        op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade() -> None:
    for table, column in reversed(INDEXES):
        op.drop_index(f"ix_{table}_{column}", table_name=table)
