"""v1.10: compras no cartão de crédito lançadas como "já pagas" voltam para em aberto

O formulário marcava "Já paga" sozinho para compras do dia; no cartão de crédito isso deixava a
compra fora do limite usado e a fatura como paga. Volta para em aberto só o que foi marcado
pago no próprio lançamento (pago até 5 minutos depois de criado) e cuja fatura ainda não
venceu. Faturas pagas de verdade em Cartões não são tocadas.

Revision ID: 0033
Revises: 0032
Create Date: 2026-11-17
"""

from collections.abc import Sequence
from datetime import date, datetime, timedelta

import sqlalchemy as sa
from alembic import op

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _when(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    return datetime.fromisoformat(str(value)).replace(tzinfo=None)


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, created_at, paid_at FROM expenses "
            "WHERE card_id IS NOT NULL AND paid IS TRUE AND paid_at IS NOT NULL "
            "AND due_date >= :today"
        ),
        {"today": date.today()},
    ).fetchall()
    ids = []
    for row in rows:
        created, paid = _when(row.created_at), _when(row.paid_at)
        if created and paid and abs(paid - created) <= timedelta(minutes=5):
            ids.append(row.id)
    for expense_id in ids:
        bind.execute(
            sa.text("UPDATE expenses SET paid = FALSE, paid_at = NULL WHERE id = :id"),
            {"id": expense_id},
        )


def downgrade() -> None:
    # Correção de dados: não há como saber quais eram as "pagas" erradas para refazer.
    pass
