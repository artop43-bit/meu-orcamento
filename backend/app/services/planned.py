"""Gastos planejados e calendário do mês.

Planejado é um gasto previsto numa data (aniversário, viagem, IPVA): entra na projeção e
no consultor até virar lançamento de verdade (um toque em "Lançar").
"""

import calendar as cal
import uuid
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.months import with_day
from app.models import Category, Expense, PlannedExpense, User
from app.services import budget


def month_end(month: date) -> date:
    return date(month.year, month.month, cal.monthrange(month.year, month.month)[1])


def list_planned(
    db: Session, user: User, start: date | None = None, end: date | None = None
) -> list[PlannedExpense]:
    stmt = select(PlannedExpense).where(PlannedExpense.user_id == user.id)
    if start is not None:
        stmt = stmt.where(PlannedExpense.date >= start)
    if end is not None:
        stmt = stmt.where(PlannedExpense.date <= end)
    return list(db.scalars(stmt.order_by(PlannedExpense.date, PlannedExpense.created_at)))


def pending_planned(db: Session, user: User, start: date, end: date) -> list[PlannedExpense]:
    """Planejados ainda não lançados no período (os que contam na projeção)."""
    return [p for p in list_planned(db, user, start, end) if p.expense_id is None]


def create_planned(db: Session, user: User, data: dict[str, Any]) -> PlannedExpense:
    budget._check_category(db, user, data.get("category_id"))
    item = PlannedExpense(user_id=user.id, **data)
    db.add(item)
    db.commit()
    return item


def update_planned(
    db: Session, user: User, item_id: uuid.UUID, changes: dict[str, Any]
) -> PlannedExpense:
    item = budget._owned(db, PlannedExpense, item_id, user)
    if "category_id" in changes:
        budget._check_category(db, user, changes["category_id"])
    budget._apply(item, changes)
    db.commit()
    return item


def delete_planned(db: Session, user: User, item_id: uuid.UUID) -> None:
    db.delete(budget._owned(db, PlannedExpense, item_id, user))
    db.commit()


def confirm_planned(db: Session, user: User, item_id: uuid.UUID, paid: bool) -> Expense:
    """Transforma o planejado em conta do mês da data (vencimento = data planejada)."""
    item = budget._owned(db, PlannedExpense, item_id, user)
    if item.expense_id is not None:
        raise AppError(409, "already_confirmed", "Este gasto planejado já foi lançado.")
    month = item.date.replace(day=1)
    budget.ensure_month(db, user, month)
    [expense] = budget.create_expense(
        db,
        user,
        month,
        {
            "description": item.description,
            "amount": item.amount,
            "category_id": item.category_id,
            "due_date": item.date,
            "notes": item.notes,
            "paid": paid,
        },
    )
    item.expense_id = expense.id
    db.commit()
    return expense


# ---------------------------------------------------------------- calendário


def month_calendar(db: Session, user: User, month: date) -> list[dict[str, Any]]:
    """Tudo o que tem data no mês: contas, parcelas, rendas e planejados, em ordem."""
    data = budget.get_month(db, user, month)
    last = month_end(month)
    categories = {c.id: c for c in db.scalars(select(Category).where(Category.user_id == user.id))}
    events: list[dict[str, Any]] = []

    def category(category_id: uuid.UUID | None) -> dict[str, Any]:
        found = categories.get(category_id) if category_id else None
        return {
            "category_id": category_id,
            "category": found.name if found else None,
            "color": found.color if found else None,
        }

    for expense in data.expenses:
        if expense.installment_group_id is not None:
            kind = "installment"
        elif expense.recurring_id is not None:
            kind = "recurring"
        else:
            kind = "expense"
        events.append(
            {
                "id": expense.id,
                "date": expense.due_date,
                "kind": kind,
                "description": expense.description,
                "amount": expense.amount,
                "paid": expense.paid,
                "installment_number": expense.installment_number,
                "installment_total": expense.installment_total,
                **category(expense.category_id),
            }
        )
    for income in data.incomes:
        events.append(
            {
                "id": income.id,
                "date": with_day(month, income.day) if income.day else None,
                "kind": "income",
                "description": income.description,
                "amount": income.amount,
                "paid": None,
                "income_type": income.income_type,
                **category(None),
            }
        )
    for planned in list_planned(db, user, month, last):
        events.append(
            {
                "id": planned.id,
                "date": planned.date,
                "kind": "planned",
                "description": planned.description,
                "amount": planned.amount,
                "paid": planned.expense_id is not None,
                "expense_id": planned.expense_id,
                "notes": planned.notes,
                **category(planned.category_id),
            }
        )
    # Primeiro os com data (em ordem), depois os sem data.
    events.sort(key=lambda e: (e["date"] is None, e["date"] or month, e["kind"] != "income"))
    return events
