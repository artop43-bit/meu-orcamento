"""v1.10.1: cota de arquivos de 100 MB por conta (mídias da Mensageria ficam fora da cota)

Revision ID: 0045
Revises: 0044
Create Date: 2026-11-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0045"
down_revision: str | None = "0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "storage_quota_mb",
            existing_type=sa.SmallInteger(),
            server_default="100",
            existing_nullable=False,
        )
    # Só contas no padrão anterior (200); cota que o administrador mudou à mão fica como está.
    op.execute("UPDATE users SET storage_quota_mb = 100 WHERE storage_quota_mb = 200")


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "storage_quota_mb",
            existing_type=sa.SmallInteger(),
            server_default="200",
            existing_nullable=False,
        )
    op.execute("UPDATE users SET storage_quota_mb = 200 WHERE storage_quota_mb = 100")
