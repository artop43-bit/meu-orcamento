"""v1.4: vale-refeição como conta, chave Pix, MEI e aviso diário

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("pix_key", sa.String(length=80), nullable=True))
        batch.add_column(sa.Column("pix_name", sa.String(length=25), nullable=True))
        batch.add_column(sa.Column("pix_city", sa.String(length=15), nullable=True))
        batch.add_column(sa.Column("mei", sa.Boolean(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("push_daily", sa.Boolean(), nullable=False, server_default="0"))
    with op.batch_alter_table("incomes") as batch:
        batch.add_column(sa.Column("mei", sa.Boolean(), nullable=False, server_default="0"))
    with op.batch_alter_table("recurring_items") as batch:
        batch.add_column(sa.Column("account_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_recurring_items_account_id",
            "money_accounts",
            ["account_id"],
            ["id"],
            ondelete="SET NULL",
        )
    with op.batch_alter_table("money_accounts") as batch:
        batch.add_column(sa.Column("benefit_category_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("recurring_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_money_accounts_benefit_category_id",
            "categories",
            ["benefit_category_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_foreign_key(
            "fk_money_accounts_recurring_id",
            "recurring_items",
            ["recurring_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("money_accounts") as batch:
        batch.drop_constraint("fk_money_accounts_recurring_id", type_="foreignkey")
        batch.drop_constraint("fk_money_accounts_benefit_category_id", type_="foreignkey")
        batch.drop_column("recurring_id")
        batch.drop_column("benefit_category_id")
    with op.batch_alter_table("recurring_items") as batch:
        batch.drop_constraint("fk_recurring_items_account_id", type_="foreignkey")
        batch.drop_column("account_id")
    with op.batch_alter_table("incomes") as batch:
        batch.drop_column("mei")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("push_daily")
        batch.drop_column("mei")
        batch.drop_column("pix_city")
        batch.drop_column("pix_name")
        batch.drop_column("pix_key")
