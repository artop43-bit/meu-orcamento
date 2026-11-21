"""v1.10.1: Precisão de 3 casas em quantidades e índices únicos de numeração e vínculos

Revision ID: 0043
Revises: 0042
Create Date: 2026-11-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0043"
down_revision: str | None = "0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("catalog_items") as batch_op:
        batch_op.alter_column(
            "stock_qty",
            existing_type=sa.Numeric(12, 2),
            type_=sa.Numeric(12, 3),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "min_stock",
            existing_type=sa.Numeric(12, 2),
            type_=sa.Numeric(12, 3),
            existing_nullable=False,
        )

    with op.batch_alter_table("catalog_movements") as batch_op:
        batch_op.alter_column(
            "qty",
            existing_type=sa.Numeric(12, 2),
            type_=sa.Numeric(12, 3),
            existing_nullable=False,
        )

    with op.batch_alter_table("commercial_orders") as batch_op:
        batch_op.create_unique_constraint(
            "uq_commercial_orders_user_number",
            ["user_id", "number"],
        )

    with op.batch_alter_table("commercial_documents") as batch_op:
        batch_op.create_unique_constraint(
            "uq_commercial_documents_user_type_number",
            ["user_id", "doc_type", "number"],
        )

    op.create_index(
        "uq_work_projects_user_deal",
        "work_projects",
        ["user_id", "crm_deal_id"],
        unique=True,
        sqlite_where=sa.text("crm_deal_id IS NOT NULL"),
        postgresql_where=sa.text("crm_deal_id IS NOT NULL"),
    )
    op.create_index(
        "uq_work_projects_user_proposal",
        "work_projects",
        ["user_id", "proposal_id"],
        unique=True,
        sqlite_where=sa.text("proposal_id IS NOT NULL"),
        postgresql_where=sa.text("proposal_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_work_projects_user_proposal", table_name="work_projects")
    op.drop_index("uq_work_projects_user_deal", table_name="work_projects")

    with op.batch_alter_table("commercial_documents") as batch_op:
        batch_op.drop_constraint("uq_commercial_documents_user_type_number", type_="unique")

    with op.batch_alter_table("commercial_orders") as batch_op:
        batch_op.drop_constraint("uq_commercial_orders_user_number", type_="unique")

    with op.batch_alter_table("catalog_movements") as batch_op:
        batch_op.alter_column(
            "qty",
            existing_type=sa.Numeric(12, 3),
            type_=sa.Numeric(12, 2),
            existing_nullable=False,
        )

    with op.batch_alter_table("catalog_items") as batch_op:
        batch_op.alter_column(
            "min_stock",
            existing_type=sa.Numeric(12, 3),
            type_=sa.Numeric(12, 2),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "stock_qty",
            existing_type=sa.Numeric(12, 3),
            type_=sa.Numeric(12, 2),
            existing_nullable=False,
        )
