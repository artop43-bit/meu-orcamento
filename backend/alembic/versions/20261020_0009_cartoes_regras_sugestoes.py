"""cartoes, regras de categoria e sugestoes

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "credit_cards",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("limit_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("closing_day", sa.SmallInteger(), nullable=False),
        sa.Column("due_day", sa.SmallInteger(), nullable=False),
        sa.Column("color", sa.String(length=7), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_credit_cards_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_credit_cards")),
    )
    op.create_index(op.f("ix_credit_cards_user_id"), "credit_cards", ["user_id"])

    with op.batch_alter_table("expenses") as batch:
        batch.add_column(sa.Column("card_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("purchase_date", sa.Date(), nullable=True))
        batch.create_foreign_key(
            op.f("fk_expenses_card_id_credit_cards"),
            "credit_cards",
            ["card_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index(op.f("ix_expenses_card_id"), ["card_id"])

    op.create_table(
        "category_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("pattern", sa.String(length=60), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_category_rules_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name=op.f("fk_category_rules_category_id_categories"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_category_rules")),
        sa.UniqueConstraint("user_id", "pattern", name=op.f("uq_category_rules_user_id")),
    )
    op.create_index(op.f("ix_category_rules_user_id"), "category_rules", ["user_id"])

    op.create_table(
        "feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("page", sa.String(length=200), nullable=True),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        sa.Column("app_version", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_feedback_user_id_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_feedback")),
    )
    op.create_index(op.f("ix_feedback_user_id"), "feedback", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_feedback_user_id"), table_name="feedback")
    op.drop_table("feedback")
    op.drop_index(op.f("ix_category_rules_user_id"), table_name="category_rules")
    op.drop_table("category_rules")
    with op.batch_alter_table("expenses") as batch:
        batch.drop_index(op.f("ix_expenses_card_id"))
        batch.drop_constraint(op.f("fk_expenses_card_id_credit_cards"), type_="foreignkey")
        batch.drop_column("purchase_date")
        batch.drop_column("card_id")
    op.drop_index(op.f("ix_credit_cards_user_id"), table_name="credit_cards")
    op.drop_table("credit_cards")
