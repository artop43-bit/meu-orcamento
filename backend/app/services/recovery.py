"""Modo sem culpa (v1.3): plano passo a passo quando o mês fecha (ou vai fechar) no negativo.

Sem julgamento e sem recomendar produto financeiro. Mostra:
1. o tamanho da diferença;
2. em quanto tempo dá para cobri-la (1, 3 ou 6 meses) e quanto isso pede por mês;
3. onde ajustar: categorias não essenciais que passaram da média dos 3 meses anteriores;
4. contas fixas não essenciais que podem ser revistas (assinaturas, serviços).
"""

from collections import defaultdict
from datetime import date
from decimal import ROUND_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.months import add_months
from app.models import Category, Expense, User
from app.services import budget, subscriptions

ZERO = Decimal("0")
CENT = Decimal("0.01")


def plan(db: Session, user: User, month: date) -> dict[str, Any]:
    data = budget.get_month(db, user, month)
    balance = data.summary["balance"]
    deficit = -balance if balance < 0 else ZERO
    if deficit == 0:
        return {"month": month, "deficit": ZERO, "spread": [], "cuts": [], "fixed": []}

    categories = {c.id: c for c in db.scalars(select(Category).where(Category.user_id == user.id))}
    past: dict[Any, Decimal] = defaultdict(lambda: ZERO)
    for expense in db.scalars(
        select(Expense).where(
            Expense.user_id == user.id,
            Expense.month >= add_months(month, -3),
            Expense.month < month,
        )
    ):
        past[expense.category_id] += expense.amount

    cuts = []
    for row in data.summary["by_category"]:
        category = categories.get(row["category_id"]) if row["category_id"] else None
        if category is not None and category.is_essential:
            continue
        average = (past[row["category_id"]] / 3).quantize(CENT)
        above = row["total"] - average if average > 0 else ZERO
        cuts.append(
            {
                "category_id": row["category_id"],
                "name": row["name"],
                "total": row["total"],
                "average": average,
                "above_average": max(above, ZERO),
            }
        )
    cuts.sort(key=lambda c: (c["above_average"], c["total"]), reverse=True)

    fixed = []
    for item in subscriptions.overview(db, user, today=month)["fixed"]:
        category = categories.get(item["category_id"]) if item["category_id"] else None
        if category is not None and category.is_essential:
            continue
        monthly = (Decimal(item["amount"]) / (item["interval_months"] or 1)).quantize(CENT)
        fixed.append({"description": item["description"], "monthly": monthly})
    fixed.sort(key=lambda f: f["monthly"], reverse=True)

    return {
        "month": month,
        "deficit": deficit,
        "spread": [
            {"months": n, "per_month": (deficit / n).quantize(CENT, rounding=ROUND_UP)}
            for n in (1, 3, 6)
        ],
        "cuts": cuts[:4],
        "fixed": fixed[:5],
    }
