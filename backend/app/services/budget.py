"""Regras do orçamento: categorias, meses, rendas, contas, parcelas, fixas, metas e histórico.

Toda consulta filtra por usuário; acessar item de outra pessoa responde "não encontrado".
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.months import add_months, current_month, parse_month, with_day
from app.db.base import Base
from app.db.types import utcnow
from app.models import BudgetMonth, Category, Expense, Goal, Income, RecurringItem, User

ZERO = Decimal("0.00")

DEFAULT_CATEGORIES: list[tuple[str, bool, str]] = [
    ("Moradia", True, "#4e79a7"),
    ("Alimentação", True, "#59a14f"),
    ("Transporte", True, "#f28e2b"),
    ("Saúde", True, "#e15759"),
    ("Educação", True, "#76b7b2"),
    ("Serviços", True, "#9c755f"),
    ("Lazer", False, "#b07aa1"),
    ("Outros", False, "#bab0ac"),
]


def _owned[ModelT: Base](
    db: Session, model: type[ModelT], item_id: uuid.UUID, user: User
) -> ModelT:
    item = db.get(model, item_id)
    if item is None or getattr(item, "user_id", None) != user.id:
        raise AppError(404, "not_found", "Item não encontrado.")
    return item


def _apply(item: Any, changes: dict[str, Any]) -> None:
    for field, value in changes.items():
        setattr(item, field, value)


# ---------------------------------------------------------------- categorias


def create_default_categories(db: Session, user: User) -> None:
    for name, essential, color in DEFAULT_CATEGORIES:
        db.add(Category(user_id=user.id, name=name, is_essential=essential, color=color))


def list_categories(db: Session, user: User) -> list[Category]:
    return list(
        db.scalars(select(Category).where(Category.user_id == user.id).order_by(Category.name))
    )


def _ensure_unique_category_name(
    db: Session, user: User, name: str, ignore_id: uuid.UUID | None = None
) -> None:
    stmt = select(Category.id).where(
        Category.user_id == user.id, func.lower(Category.name) == name.lower()
    )
    if ignore_id is not None:
        stmt = stmt.where(Category.id != ignore_id)
    if db.scalar(stmt) is not None:
        raise AppError(409, "category_exists", "Já existe uma categoria com esse nome.")


def create_category(db: Session, user: User, data: dict[str, Any]) -> Category:
    _ensure_unique_category_name(db, user, data["name"])
    category = Category(user_id=user.id, **data)
    db.add(category)
    db.commit()
    return category


def update_category(
    db: Session, user: User, category_id: uuid.UUID, changes: dict[str, Any]
) -> Category:
    category = _owned(db, Category, category_id, user)
    if changes.get("name"):
        _ensure_unique_category_name(db, user, changes["name"], ignore_id=category.id)
    _apply(category, changes)
    db.commit()
    return category


def delete_category(db: Session, user: User, category_id: uuid.UUID) -> None:
    category = _owned(db, Category, category_id, user)
    # As contas ficam "sem categoria" (ON DELETE SET NULL, feito aqui também
    # para bancos sem chave estrangeira ativa).
    for model in (Expense, RecurringItem):
        for item in db.scalars(select(model).where(model.category_id == category.id)):
            item.category_id = None
    db.delete(category)
    db.commit()


def _check_category(db: Session, user: User, category_id: uuid.UUID | None) -> None:
    if category_id is not None:
        _owned(db, Category, category_id, user)


# ---------------------------------------------------------------- meses e fixas


def _materialize(db: Session, item: RecurringItem, month: date) -> None:
    """Lança a conta/renda fixa no mês, se ainda não estiver lá."""
    model = Income if item.kind == "income" else Expense
    exists = db.scalar(select(model.id).where(model.recurring_id == item.id, model.month == month))
    if exists is not None:
        return
    if item.kind == "income":
        db.add(
            Income(
                user_id=item.user_id,
                month=month,
                description=item.description,
                amount=item.amount,
                recurring_id=item.id,
            )
        )
    else:
        db.add(
            Expense(
                user_id=item.user_id,
                month=month,
                description=item.description,
                amount=item.amount,
                category_id=item.category_id,
                due_date=with_day(month, item.due_day) if item.due_day else None,
                recurring_id=item.id,
            )
        )


def _active_in(item: RecurringItem, month: date) -> bool:
    return item.start_month <= month and (item.end_month is None or month <= item.end_month)


def ensure_month(db: Session, user: User, month: date) -> None:
    """Na primeira vez que um mês é aberto, lança nele as contas e rendas fixas."""
    exists = db.scalar(
        select(BudgetMonth.id).where(BudgetMonth.user_id == user.id, BudgetMonth.month == month)
    )
    if exists is not None:
        return
    db.add(BudgetMonth(user_id=user.id, month=month))
    for item in db.scalars(select(RecurringItem).where(RecurringItem.user_id == user.id)):
        if _active_in(item, month):
            _materialize(db, item, month)
    db.commit()


def list_recurring(db: Session, user: User) -> list[RecurringItem]:
    return list(
        db.scalars(
            select(RecurringItem)
            .where(RecurringItem.user_id == user.id)
            .order_by(RecurringItem.kind, RecurringItem.description)
        )
    )


def _validate_period(start: date, end: date | None) -> None:
    if end is not None and end < start:
        raise AppError(400, "invalid_period", "O mês final não pode ser antes do inicial.")


def create_recurring(db: Session, user: User, data: dict[str, Any]) -> RecurringItem:
    start = parse_month(data.pop("start_month"))
    end = parse_month(data["end_month"]) if data.get("end_month") else None
    data.pop("end_month", None)
    _validate_period(start, end)
    if data["kind"] == "income":
        data["category_id"] = None
        data["due_day"] = None
    _check_category(db, user, data.get("category_id"))

    item = RecurringItem(user_id=user.id, start_month=start, end_month=end, **data)
    db.add(item)
    db.flush()
    # Meses já abertos dentro do período recebem o lançamento na hora.
    for (month,) in db.execute(
        select(BudgetMonth.month).where(BudgetMonth.user_id == user.id, BudgetMonth.month >= start)
    ):
        if _active_in(item, month):
            _materialize(db, item, month)
    db.commit()
    return item


def update_recurring(
    db: Session, user: User, item_id: uuid.UUID, changes: dict[str, Any]
) -> RecurringItem:
    item = _owned(db, RecurringItem, item_id, user)
    if "end_month" in changes:
        changes["end_month"] = parse_month(changes["end_month"]) if changes["end_month"] else None
        _validate_period(item.start_month, changes["end_month"])
    if item.kind == "income":
        changes.pop("category_id", None)
        changes.pop("due_day", None)
    _check_category(db, user, changes.get("category_id"))
    _apply(item, changes)

    # Propaga para os lançamentos a partir do mês atual que ainda não foram pagos.
    this_month = current_month()
    if item.kind == "income":
        instances: list[Income | Expense] = list(
            db.scalars(
                select(Income).where(Income.recurring_id == item.id, Income.month >= this_month)
            )
        )
    else:
        instances = list(
            db.scalars(
                select(Expense).where(
                    Expense.recurring_id == item.id,
                    Expense.month >= this_month,
                    Expense.paid.is_(False),
                )
            )
        )
    for instance in instances:
        if item.end_month is not None and instance.month > item.end_month:
            db.delete(instance)
            continue
        instance.description = item.description
        instance.amount = item.amount
        if isinstance(instance, Expense):
            instance.category_id = item.category_id
            instance.due_date = with_day(instance.month, item.due_day) if item.due_day else None
    db.commit()
    return item


def delete_recurring(db: Session, user: User, item_id: uuid.UUID) -> None:
    """Remove a fixa e os lançamentos futuros; mantém o mês atual e os anteriores."""
    item = _owned(db, RecurringItem, item_id, user)
    after = current_month()
    for model in (Income, Expense):
        db.execute(delete(model).where(model.recurring_id == item.id, model.month > after))
        for instance in db.scalars(select(model).where(model.recurring_id == item.id)):
            instance.recurring_id = None
    db.delete(item)
    db.commit()


def _end_recurrence_before(db: Session, item_id: uuid.UUID | None, month: date) -> None:
    """Encerra a fixa no mês anterior e remove os lançamentos deste mês em diante."""
    if item_id is None:
        return
    item = db.get(RecurringItem, item_id)
    if item is None:
        return
    for model in (Income, Expense):
        db.execute(delete(model).where(model.recurring_id == item.id, model.month >= month))
    previous = add_months(month, -1)
    if previous < item.start_month:
        for model in (Income, Expense):
            for instance in db.scalars(select(model).where(model.recurring_id == item.id)):
                instance.recurring_id = None
        db.delete(item)
    else:
        item.end_month = previous


# ---------------------------------------------------------------- rendas


def create_income(db: Session, user: User, month: date, data: dict[str, Any]) -> Income:
    income = Income(user_id=user.id, month=month, **data)
    db.add(income)
    db.commit()
    return income


def update_income(db: Session, user: User, income_id: uuid.UUID, changes: dict[str, Any]) -> Income:
    income = _owned(db, Income, income_id, user)
    _apply(income, changes)
    db.commit()
    return income


def delete_income(db: Session, user: User, income_id: uuid.UUID, scope: str) -> None:
    income = _owned(db, Income, income_id, user)
    if scope == "following" and income.recurring_id is not None:
        _end_recurrence_before(db, income.recurring_id, income.month)
    else:
        db.delete(income)
    db.commit()


# ---------------------------------------------------------------- contas


def create_expense(db: Session, user: User, month: date, data: dict[str, Any]) -> list[Expense]:
    installments = data.pop("installments", None)
    _check_category(db, user, data.get("category_id"))

    if not installments:
        expense = Expense(user_id=user.id, month=month, **data)
        db.add(expense)
        db.commit()
        return [expense]

    group = uuid.uuid4()
    due = data.pop("due_date", None)
    created = []
    for index in range(installments):
        installment_month = add_months(month, index)
        expense = Expense(
            user_id=user.id,
            month=installment_month,
            due_date=with_day(installment_month, due.day) if due else None,
            installment_group_id=group,
            installment_number=index + 1,
            installment_total=installments,
            **data,
        )
        db.add(expense)
        created.append(expense)
    db.commit()
    return created


def update_expense(
    db: Session, user: User, expense_id: uuid.UUID, changes: dict[str, Any]
) -> Expense:
    expense = _owned(db, Expense, expense_id, user)
    if "category_id" in changes:
        _check_category(db, user, changes["category_id"])
    if "paid" in changes and changes["paid"] is not None and changes["paid"] != expense.paid:
        expense.paid_at = utcnow() if changes["paid"] else None
    if changes.get("paid") is None:
        changes.pop("paid", None)
    _apply(expense, changes)
    db.commit()
    return expense


def delete_expense(db: Session, user: User, expense_id: uuid.UUID, scope: str) -> None:
    expense = _owned(db, Expense, expense_id, user)
    if scope == "following" and expense.installment_group_id is not None:
        db.execute(
            delete(Expense).where(
                Expense.user_id == user.id,
                Expense.installment_group_id == expense.installment_group_id,
                Expense.installment_number >= (expense.installment_number or 1),
            )
        )
    elif scope == "following" and expense.recurring_id is not None:
        _end_recurrence_before(db, expense.recurring_id, expense.month)
    else:
        db.delete(expense)
    db.commit()


# ---------------------------------------------------------------- visão do mês


@dataclass
class MonthData:
    month: date
    incomes: list[Income]
    expenses: list[Expense]
    summary: dict[str, Any]


def _pct(part: Decimal, whole: Decimal) -> float | None:
    if whole <= 0:
        return None
    return round(float(part / whole * 100), 1)


def get_month(db: Session, user: User, month: date) -> MonthData:
    ensure_month(db, user, month)
    incomes = list(
        db.scalars(
            select(Income)
            .where(Income.user_id == user.id, Income.month == month)
            .order_by(Income.created_at)
        )
    )
    expenses = list(
        db.scalars(
            select(Expense)
            .where(Expense.user_id == user.id, Expense.month == month)
            .order_by(Expense.due_date.is_(None), Expense.due_date, Expense.created_at)
        )
    )
    categories = {c.id: c for c in list_categories(db, user)}

    income_total = sum((i.amount for i in incomes), ZERO)
    expense_total = sum((e.amount for e in expenses), ZERO)
    paid_total = sum((e.amount for e in expenses if e.paid), ZERO)

    by_category: dict[uuid.UUID | None, Decimal] = defaultdict(lambda: ZERO)
    for expense in expenses:
        by_category[expense.category_id] += expense.amount

    essential_total = ZERO
    category_totals = []
    for category_id, total in by_category.items():
        category = categories.get(category_id) if category_id else None
        essential = bool(category and category.is_essential)
        if essential:
            essential_total += total
        category_totals.append(
            {
                "category_id": category_id,
                "name": category.name if category else "Sem categoria",
                "is_essential": essential,
                "total": total,
            }
        )
    category_totals.sort(key=lambda c: c["total"], reverse=True)

    summary = {
        "income_total": income_total,
        "expense_total": expense_total,
        "paid_total": paid_total,
        "pending_total": expense_total - paid_total,
        "balance": income_total - expense_total,
        "committed_pct": _pct(expense_total, income_total),
        "essential_total": essential_total,
        "non_essential_total": expense_total - essential_total,
        "by_category": category_totals,
    }
    return MonthData(month=month, incomes=incomes, expenses=expenses, summary=summary)


def history(db: Session, user: User, until: date, months: int) -> list[dict[str, Any]]:
    start = add_months(until, -(months - 1))

    def totals(stmt: Any) -> dict[date, Decimal]:
        return {month: Decimal(total) for month, total in db.execute(stmt)}

    incomes = totals(
        select(Income.month, func.sum(Income.amount))
        .where(Income.user_id == user.id, Income.month.between(start, until))
        .group_by(Income.month)
    )
    expenses = totals(
        select(Expense.month, func.sum(Expense.amount))
        .where(Expense.user_id == user.id, Expense.month.between(start, until))
        .group_by(Expense.month)
    )
    paid = totals(
        select(Expense.month, func.sum(Expense.amount))
        .where(
            Expense.user_id == user.id,
            Expense.month.between(start, until),
            Expense.paid.is_(True),
        )
        .group_by(Expense.month)
    )

    points = []
    for index in range(months):
        month = add_months(start, index)
        income = incomes.get(month, ZERO)
        expense = expenses.get(month, ZERO)
        points.append(
            {
                "month": month,
                "income": income,
                "expenses": expense,
                "paid": paid.get(month, ZERO),
                "balance": income - expense,
                "committed_pct": _pct(expense, income),
                "has_data": month in incomes or month in expenses,
            }
        )
    return points


# ---------------------------------------------------------------- metas


def list_goals(db: Session, user: User) -> list[Goal]:
    return list(db.scalars(select(Goal).where(Goal.user_id == user.id).order_by(Goal.created_at)))


def create_goal(db: Session, user: User, data: dict[str, Any]) -> Goal:
    goal = Goal(user_id=user.id, **data)
    db.add(goal)
    db.commit()
    return goal


def update_goal(db: Session, user: User, goal_id: uuid.UUID, changes: dict[str, Any]) -> Goal:
    goal = _owned(db, Goal, goal_id, user)
    _apply(goal, changes)
    db.commit()
    return goal


def contribute_to_goal(db: Session, user: User, goal_id: uuid.UUID, amount: Decimal) -> Goal:
    goal = _owned(db, Goal, goal_id, user)
    if amount == 0:
        raise AppError(400, "invalid_amount", "Informe um valor diferente de zero.")
    new_amount = goal.current_amount + amount
    if new_amount < 0:
        raise AppError(400, "invalid_amount", "A retirada é maior que o valor guardado na meta.")
    goal.current_amount = new_amount
    db.commit()
    return goal


def delete_goal(db: Session, user: User, goal_id: uuid.UUID) -> None:
    db.delete(_owned(db, Goal, goal_id, user))
    db.commit()


def goal_progress(goal: Goal) -> float:
    if goal.target_amount <= 0:
        return 0.0
    return round(min(float(goal.current_amount / goal.target_amount * 100), 100.0), 1)
