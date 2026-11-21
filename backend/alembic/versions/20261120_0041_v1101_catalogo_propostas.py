"""v1.10.1: Catálogo, estoque, pedidos comerciais e documentos em PDF

Revision ID: 0041
Revises: 0040
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0041"
down_revision: str | None = "0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "catalog_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="product"),
        sa.Column("sku", sa.String(length=40), nullable=True),
        sa.Column("name", sa.String(length=140), nullable=False),
        sa.Column("unit", sa.String(length=16), nullable=False, server_default="un"),
        sa.Column("cost_price", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("sale_price", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("stock_qty", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("min_stock", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_catalog_items_user_id", "catalog_items", ["user_id"])
    op.create_index("ix_catalog_items_user_name", "catalog_items", ["user_id", "name"])

    op.create_table(
        "commercial_orders",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column(
            "contact_id",
            sa.Uuid(),
            sa.ForeignKey("crm_contacts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("customer_name", sa.String(length=140), nullable=False),
        sa.Column("items_json", sa.JSON(), nullable=False),
        sa.Column("discount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("total_cost", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column(
            "crm_deal_id",
            sa.Uuid(),
            sa.ForeignKey("crm_deals.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "budget_income_id",
            sa.Uuid(),
            sa.ForeignKey("incomes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_commercial_orders_user_id", "commercial_orders", ["user_id"])
    op.create_index("ix_commercial_orders_contact_id", "commercial_orders", ["contact_id"])
    op.create_index("ix_commercial_orders_crm_deal_id", "commercial_orders", ["crm_deal_id"])
    op.create_index(
        "ix_commercial_orders_budget_income_id", "commercial_orders", ["budget_income_id"]
    )
    op.create_index(
        "ix_commercial_orders_user_created",
        "commercial_orders",
        ["user_id", "created_at"],
    )

    op.create_table(
        "catalog_movements",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "item_id",
            sa.Uuid(),
            sa.ForeignKey("catalog_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("qty", sa.Numeric(12, 2), nullable=False),
        sa.Column("reason", sa.String(length=180), nullable=True),
        sa.Column(
            "order_id",
            sa.Uuid(),
            sa.ForeignKey("commercial_orders.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_catalog_movements_user_id", "catalog_movements", ["user_id"])
    op.create_index("ix_catalog_movements_item_id", "catalog_movements", ["item_id"])
    op.create_index("ix_catalog_movements_order_id", "catalog_movements", ["order_id"])
    op.create_index(
        "ix_catalog_movements_item_created",
        "catalog_movements",
        ["item_id", "created_at"],
    )

    op.create_table(
        "commercial_documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("doc_type", sa.String(length=20), nullable=False, server_default="proposal"),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column(
            "contact_id",
            sa.Uuid(),
            sa.ForeignKey("crm_contacts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "crm_deal_id",
            sa.Uuid(),
            sa.ForeignKey("crm_deals.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "order_id",
            sa.Uuid(),
            sa.ForeignKey("commercial_orders.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("customer_name", sa.String(length=140), nullable=False),
        sa.Column("customer_doc", sa.String(length=40), nullable=True),
        sa.Column("customer_contact", sa.String(length=120), nullable=True),
        sa.Column("items_json", sa.JSON(), nullable=False),
        sa.Column("discount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("terms_text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column(
            "budget_income_id",
            sa.Uuid(),
            sa.ForeignKey("incomes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_commercial_documents_user_id", "commercial_documents", ["user_id"])
    op.create_index("ix_commercial_documents_contact_id", "commercial_documents", ["contact_id"])
    op.create_index("ix_commercial_documents_crm_deal_id", "commercial_documents", ["crm_deal_id"])
    op.create_index("ix_commercial_documents_order_id", "commercial_documents", ["order_id"])
    op.create_index(
        "ix_commercial_documents_budget_income_id",
        "commercial_documents",
        ["budget_income_id"],
    )
    op.create_index(
        "ix_commercial_documents_user_type_created",
        "commercial_documents",
        ["user_id", "doc_type", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("commercial_documents")
    op.drop_table("catalog_movements")
    op.drop_table("commercial_orders")
    op.drop_table("catalog_items")
