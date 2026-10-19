"""Assinaturas e contas fixas: custo mensal/anual e detecção do que se repete sem ser fixa."""

from collections import defaultdict
from datetime import date
from decimal import Decimal
from statistics import median
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.months import add_months, format_month
from app.models import Expense, RecurringItem, User
from app.services import budget
from app.services.suggest import normalize

ZERO = Decimal("0.00")
WINDOW = 6  # meses olhados para trás
MIN_MONTHS = 3  # aparece em pelo menos 3 meses diferentes
TOLERANCE = Decimal("0.20")  # valores parecidos: até 20% da mediana


def overview(db: Session, user: User, today: date | None = None) -> dict[str, Any]:
    this_month = budget.current_month() if today is None else today.replace(day=1)
    fixed = []
    for item in budget.list_recurring(db, user):
        if item.kind != "expense":
            continue
        if item.end_month is not None and item.end_month < this_month:
            continue
        interval = item.interval_months or 1
        fixed.append(
            {
                "id": item.id,
                "description": item.description,
                "amount": item.amount,
                "interval_months": interval,
                "category_id": item.category_id,
                "monthly": (item.amount / interval).quantize(Decimal("0.01")),
                "yearly": (item.amount * 12 / interval).quantize(Decimal("0.01")),
            }
        )
    fixed.sort(key=lambda f: f["yearly"], reverse=True)

    since = add_months(this_month, -WINDOW)
    groups: dict[str, list[Expense]] = defaultdict(list)
    for expense in db.scalars(
        select(Expense).where(
            Expense.user_id == user.id,
            Expense.month >= since,
            Expense.month <= this_month,
            Expense.recurring_id.is_(None),
            Expense.installment_group_id.is_(None),
        )
    ):
        groups[normalize(expense.description)].append(expense)

    fixed_names = {normalize(f["description"]) for f in fixed}
    candidates = []
    for key, items in groups.items():
        if not key or key in fixed_names:
            continue
        months = {e.month for e in items}
        recent = {m for m in months if m >= add_months(this_month, -3)}
        if len(months) < MIN_MONTHS or len(recent) < 2:
            continue
        amounts = [e.amount for e in items]
        middle = Decimal(median(amounts))
        if middle <= 0 or any(abs(a - middle) > middle * TOLERANCE for a in amounts):
            continue
        last = max(items, key=lambda e: (e.month, e.created_at))
        candidates.append(
            {
                "description": last.description,
                "amount": last.amount,
                "category_id": last.category_id,
                "due_day": last.due_date.day if last.due_date else None,
                "months": sorted(format_month(m) for m in months),
                "yearly": (middle * 12).quantize(Decimal("0.01")),
            }
        )
    candidates.sort(key=lambda c: c["yearly"], reverse=True)

    return {
        "fixed": fixed,
        "candidates": candidates,
        "monthly_total": sum((f["monthly"] for f in fixed), ZERO),
        "yearly_total": sum((f["yearly"] for f in fixed), ZERO),
    }


def promote(db: Session, user: User, data: dict[str, Any]) -> RecurringItem:
    """Transforma um gasto que se repete em conta fixa, a partir do próximo mês."""
    start = add_months(budget.current_month(), 1)
    return budget.create_recurring(
        db,
        user,
        {
            "kind": "expense",
            "description": data["description"],
            "amount": data["amount"],
            "category_id": data.get("category_id"),
            "due_day": data.get("due_day"),
            "start_month": format_month(start),
            "end_month": None,
        },
    )
