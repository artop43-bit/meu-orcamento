"""Limite por categoria com sobra para o mês seguinte (v1.3, opcional por categoria).

Com a opção ligada, o que não foi gasto do limite num mês soma ao limite do mês seguinte:
limite de R$ 300 em Lazer com R$ 80 gastos → o próximo mês começa com R$ 520. O acúmulo
começa no mês em que a opção foi ligada (carry_since) e nunca fica negativo: estourar o
limite num mês não tira do seguinte.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.months import add_months
from app.models import Category, Expense, User

ZERO = Decimal("0")


@dataclass(frozen=True)
class Limit:
    base: Decimal  # limite definido na categoria
    carried: Decimal  # sobra trazida dos meses anteriores

    @property
    def total(self) -> Decimal:
        return self.base + self.carried


def for_month(
    db: Session, user: User, month: date, categories: dict[uuid.UUID, Category]
) -> dict[uuid.UUID, Limit]:
    """Limite de cada categoria no mês, já com a sobra acumulada (quando ligada)."""
    result = {c.id: Limit(c.monthly_limit, ZERO) for c in categories.values() if c.monthly_limit}
    rolling = [
        c
        for c in categories.values()
        if c.monthly_limit and c.carry_over and c.carry_since and c.carry_since < month
    ]
    if not rolling:
        return result
    start = min(c.carry_since for c in rolling if c.carry_since)
    spent: dict[tuple[uuid.UUID, date], Decimal] = defaultdict(lambda: ZERO)
    for category_id, expense_month, total in db.execute(
        select(Expense.category_id, Expense.month, func.sum(Expense.amount))
        .where(
            Expense.user_id == user.id,
            Expense.category_id.in_([c.id for c in rolling]),
            Expense.month >= start,
            Expense.month < month,
        )
        .group_by(Expense.category_id, Expense.month)
    ):
        spent[(category_id, expense_month)] = Decimal(total)
    for category in rolling:
        assert category.monthly_limit is not None and category.carry_since is not None
        carried = ZERO
        current = category.carry_since
        while current < month:
            available = category.monthly_limit + carried
            carried = max(ZERO, available - spent[(category.id, current)])
            current = add_months(current, 1)
        result[category.id] = Limit(category.monthly_limit, carried)
    return result
