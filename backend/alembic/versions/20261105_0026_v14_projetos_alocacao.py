"""v1.4: projetos/etiquetas nas despesas e meta de alocação da carteira

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("budget", sa.Numeric(12, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "name"),
    )
    op.create_index("ix_projects_user_id", "projects", ["user_id"])
    with op.batch_alter_table("expenses") as batch:
        batch.add_column(sa.Column("project_id", sa.Uuid(), nullable=True))
        batch.create_index("ix_expenses_project_id", ["project_id"])
        batch.create_foreign_key(
            "fk_expenses_project_id", "projects", ["project_id"], ["id"], ondelete="SET NULL"
        )
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("investment_targets", sa.String(length=400), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("investment_targets")
    with op.batch_alter_table("expenses") as batch:
        batch.drop_constraint("fk_expenses_project_id", type_="foreignkey")
        batch.drop_index("ix_expenses_project_id")
        batch.drop_column("project_id")
    op.drop_index("ix_projects_user_id", table_name="projects")
    op.drop_table("projects")
