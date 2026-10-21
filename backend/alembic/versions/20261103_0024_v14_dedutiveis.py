"""v1.4: categorias dedutíveis no Imposto de Renda

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-03

As categorias padrão "Saúde" e "Educação" que já existem passam a ser dedutíveis.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("categories") as batch:
        batch.add_column(sa.Column("deductible", sa.String(length=12), nullable=True))
    op.execute("UPDATE categories SET deductible = 'saude' WHERE name = 'Saúde'")
    op.execute("UPDATE categories SET deductible = 'educacao' WHERE name = 'Educação'")


def downgrade() -> None:
    with op.batch_alter_table("categories") as batch:
        batch.drop_column("deductible")
