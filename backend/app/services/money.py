"""Contas e saldos, transferências, despesas para revisar, busca, ritmo por categoria e
cópia do mês anterior (v0.7)."""

import calendar as cal
import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.months import (
    add_months,
    cycle_date,
    cycle_range,
    format_month,
    month_of,
    with_day,
)
from app.models import (
    Category,
    CreditCard,
    Expense,
    Income,
    MoneyAccount,
    RecurringItem,
    Transfer,
    User,
)
from app.services import budget
from app.services.suggest import normalize

ZERO = Decimal("0.00")

# ---------------------------------------------------------------- contas


def _with_benefit(db: Session, account: MoneyAccount) -> MoneyAccount:
    """Vale (v1.4): expõe o valor e o dia da recarga (guardados na renda fixa ligada)."""
    item = db.get(RecurringItem, account.recurring_id) if account.recurring_id else None
    account.benefit_amount = item.amount if item else None  # type: ignore[attr-defined]
    account.benefit_day = item.due_day if item else None  # type: ignore[attr-defined]
    return account


def list_accounts(db: Session, user: User, include_archived: bool = False) -> list[MoneyAccount]:
    stmt = select(MoneyAccount).where(MoneyAccount.user_id == user.id)
    if not include_archived:
        stmt = stmt.where(MoneyAccount.archived.is_(False))
    return [_with_benefit(db, a) for a in db.scalars(stmt.order_by(MoneyAccount.created_at))]


def _sync_benefit(
    db: Session, user: User, account: MoneyAccount, amount: Decimal | None, day: int | None
) -> None:
    """Recarga do vale = renda fixa ligada à conta (entra no orçamento e no saldo do vale)."""
    item = db.get(RecurringItem, account.recurring_id) if account.recurring_id else None
    this_month = budget.current_month(user.month_start_day)
    if account.kind != "benefit" or not amount:
        if item is not None:
            _end_benefit(db, user, item, this_month)
            account.recurring_id = None
        return
    if item is None:
        item = RecurringItem(
            user_id=user.id,
            kind="income",
            description=f"Recarga: {account.name}"[:120],
            amount=amount,
            income_type="fixed",
            due_day=day,
            start_month=this_month,
            account_id=account.id,
        )
        db.add(item)
        db.flush()
        account.recurring_id = item.id
        budget._materialize_opened(db, user, item, this_month)
        return
    budget.update_recurring(
        db,
        user,
        item.id,
        {"amount": amount, "due_day": day, "description": f"Recarga: {account.name}"[:120]},
        from_month=this_month,
    )


def _end_benefit(db: Session, user: User, item: RecurringItem, this_month: date) -> None:
    """Para a recarga a partir deste mês (as já recebidas ficam no histórico)."""
    if item.start_month >= this_month:
        for income in db.scalars(select(Income).where(Income.recurring_id == item.id)):
            db.delete(income)
        db.delete(item)
        return
    budget.update_recurring(
        db, user, item.id, {"end_month": format_month(add_months(this_month, -1))}
    )


def _benefit_fields(db: Session, user: User, data: dict[str, Any]) -> tuple[Any, Any]:
    amount = data.pop("benefit_amount", None)
    day = data.pop("benefit_day", None)
    if data.get("benefit_category_id") is not None:
        budget._check_category(db, user, data["benefit_category_id"])
    return amount, day


def create_account(db: Session, user: User, data: dict[str, Any]) -> MoneyAccount:
    amount, day = _benefit_fields(db, user, data)
    if data.get("kind") == "benefit" and data.get("benefit_category_id") is None:
        food = db.scalar(
            select(Category).where(Category.user_id == user.id, Category.name == "Alimentação")
        )
        data["benefit_category_id"] = food.id if food else None
    account = MoneyAccount(user_id=user.id, **data)
    db.add(account)
    db.flush()
    _sync_benefit(db, user, account, amount, day)
    db.commit()
    return _with_benefit(db, account)


def update_account(
    db: Session, user: User, account_id: uuid.UUID, changes: dict[str, Any]
) -> MoneyAccount:
    account = budget._owned(db, MoneyAccount, account_id, user)
    touches_benefit = "benefit_amount" in changes or "benefit_day" in changes or "kind" in changes
    amount, day = _benefit_fields(db, user, changes)
    budget._apply(account, changes)
    if touches_benefit:
        current = _with_benefit(db, account)
        _sync_benefit(
            db,
            user,
            account,
            amount if amount is not None else current.benefit_amount,  # type: ignore[attr-defined]
            day if day is not None else current.benefit_day,  # type: ignore[attr-defined]
        )
    db.commit()
    return _with_benefit(db, account)


def delete_account(db: Session, user: User, account_id: uuid.UUID) -> None:
    """Exclui a conta; os lançamentos ficam sem conta e as transferências dela somem."""
    account = budget._owned(db, MoneyAccount, account_id, user)
    if account.recurring_id:
        item = db.get(RecurringItem, account.recurring_id)
        account.recurring_id = None
        if item is not None:
            _end_benefit(db, user, item, budget.current_month(user.month_start_day))
    for model in (Expense, Income, CreditCard):
        for item in db.scalars(select(model).where(model.account_id == account.id)):
            item.account_id = None
    db.delete(account)
    db.commit()


def check_account(db: Session, user: User, account_id: uuid.UUID | None) -> None:
    if account_id is not None:
        budget._owned(db, MoneyAccount, account_id, user)


def balances(db: Session, user: User, today: date | None = None) -> list[dict[str, Any]]:
    """Saldo de hoje e previsto para o fim do mês de cada conta.

    Hoje = saldo inicial + receitas já recebidas (dia passado ou sem dia, até este mês)
    − despesas pagas (inclusive faturas pagas do cartão ligado à conta) ± transferências.
    Fim do mês = hoje + receitas que ainda chegam no mês − despesas do mês ainda não pagas.
    """
    today = today or date.today()
    start_day = user.month_start_day
    month = month_of(today, start_day)
    end = cycle_range(month, start_day)[1]
    accounts = list_accounts(db, user)
    ids = {a.id for a in accounts}
    card_account = {
        c.id: c.account_id
        for c in db.scalars(select(CreditCard).where(CreditCard.user_id == user.id))
        if c.account_id
    }
    now: dict[uuid.UUID, Decimal] = defaultdict(lambda: ZERO)
    coming: dict[uuid.UUID, Decimal] = defaultdict(lambda: ZERO)

    for income in db.scalars(
        select(Income).where(
            Income.user_id == user.id, Income.account_id.in_(ids), Income.month <= month
        )
    ):
        received = (
            income.month < month
            or income.day is None
            or cycle_date(month, income.day, start_day) <= today
        )
        (now if received else coming)[income.account_id] += income.amount  # type: ignore[index]

    for expense in db.scalars(
        select(Expense).where(
            Expense.user_id == user.id,
            Expense.month <= month,
            or_(Expense.account_id.in_(ids), Expense.card_id.in_(list(card_account))),
        )
    ):
        account_id = expense.account_id or card_account.get(expense.card_id)  # type: ignore[arg-type]
        if account_id not in ids:
            continue
        if expense.paid:
            now[account_id] -= expense.amount
        elif expense.month == month:
            coming[account_id] -= expense.amount

    for transfer in db.scalars(
        select(Transfer).where(Transfer.user_id == user.id, Transfer.date <= end)
    ):
        target = now if transfer.date <= today else coming
        target[transfer.from_account_id] -= transfer.amount
        target[transfer.to_account_id] += transfer.amount

    result = []
    for account in accounts:
        current = account.initial_balance + now[account.id]
        result.append(
            {
                "account": account,
                "balance": current,
                "end_of_month": current + coming[account.id],
            }
        )
    return result


# ---------------------------------------------------------------- transferências


def list_transfers(db: Session, user: User, month: date | None = None) -> list[Transfer]:
    stmt = select(Transfer).where(Transfer.user_id == user.id)
    if month is not None:
        last = with_day(month, cal.monthrange(month.year, month.month)[1])
        stmt = stmt.where(Transfer.date >= month, Transfer.date <= last)
    return list(db.scalars(stmt.order_by(Transfer.date.desc(), Transfer.created_at.desc())))


def create_transfer(db: Session, user: User, data: dict[str, Any]) -> Transfer:
    if data["from_account_id"] == data["to_account_id"]:
        raise AppError(400, "same_account", "Escolha contas diferentes para a transferência.")
    check_account(db, user, data["from_account_id"])
    check_account(db, user, data["to_account_id"])
    transfer = Transfer(user_id=user.id, **data)
    db.add(transfer)
    db.commit()
    return transfer


def delete_transfer(db: Session, user: User, transfer_id: uuid.UUID) -> None:
    db.delete(budget._owned(db, Transfer, transfer_id, user))
    db.commit()


# ---------------------------------------------------------------- para revisar


def review_queue(db: Session, user: User) -> list[Expense]:
    return list(
        db.scalars(
            select(Expense)
            .where(Expense.user_id == user.id, Expense.needs_review.is_(True))
            .order_by(Expense.due_date.desc(), Expense.created_at.desc())
        )
    )


def confirm_review(
    db: Session,
    user: User,
    ids: list[uuid.UUID],
    category_id: uuid.UUID | None = None,
    categories: dict[uuid.UUID, uuid.UUID | None] | None = None,
) -> int:
    """Marca como conferidas. Pode definir a mesma categoria para todas ou uma por despesa."""
    if category_id is not None:
        budget._check_category(db, user, category_id)
    for value in (categories or {}).values():
        budget._check_category(db, user, value)
    items = list(db.scalars(select(Expense).where(Expense.user_id == user.id, Expense.id.in_(ids))))
    for expense in items:
        expense.needs_review = False
        if category_id is not None:
            expense.category_id = category_id
        elif categories and expense.id in categories:
            expense.category_id = categories[expense.id]
    db.commit()
    return len(items)


# ---------------------------------------------------------------- busca


def search(
    db: Session,
    user: User,
    q: str = "",
    start: date | None = None,
    end: date | None = None,
    min_amount: Decimal | None = None,
    max_amount: Decimal | None = None,
    payment_method: str | None = None,
    category_id: uuid.UUID | None = None,
    kind: str = "all",
    limit: int = 300,
) -> dict[str, Any]:
    """Despesas e receitas de todos os meses que combinam com os filtros."""
    text = normalize(q)
    results: list[dict[str, Any]] = []
    if kind in ("all", "expense"):
        stmt = select(Expense).where(Expense.user_id == user.id)
        if start:
            stmt = stmt.where(Expense.month >= start.replace(day=1))
        if end:
            stmt = stmt.where(Expense.month <= end.replace(day=1))
        if min_amount is not None:
            stmt = stmt.where(Expense.amount >= min_amount)
        if max_amount is not None:
            stmt = stmt.where(Expense.amount <= max_amount)
        if payment_method:
            stmt = stmt.where(Expense.payment_method == payment_method)
        if category_id:
            stmt = stmt.where(Expense.category_id == category_id)
        for e in db.scalars(stmt.order_by(Expense.month.desc(), Expense.due_date.desc())):
            if text and text not in normalize(f"{e.description} {e.notes or ''}"):
                continue
            results.append(
                {
                    "id": e.id,
                    "kind": "expense",
                    "month": e.month,
                    "date": e.due_date or e.purchase_date,
                    "description": e.description,
                    "amount": e.amount,
                    "category_id": e.category_id,
                    "payment_method": e.payment_method,
                    "paid": e.paid,
                }
            )
    if kind in ("all", "income") and not category_id and not payment_method:
        stmt = select(Income).where(Income.user_id == user.id)
        if start:
            stmt = stmt.where(Income.month >= start.replace(day=1))
        if end:
            stmt = stmt.where(Income.month <= end.replace(day=1))
        if min_amount is not None:
            stmt = stmt.where(Income.amount >= min_amount)
        if max_amount is not None:
            stmt = stmt.where(Income.amount <= max_amount)
        for i in db.scalars(stmt.order_by(Income.month.desc())):
            if text and text not in normalize(f"{i.description} {i.notes or ''}"):
                continue
            results.append(
                {
                    "id": i.id,
                    "kind": "income",
                    "month": i.month,
                    "date": with_day(i.month, i.day) if i.day else None,
                    "description": i.description,
                    "amount": i.amount,
                    "category_id": None,
                    "payment_method": None,
                    "paid": None,
                }
            )
    results.sort(key=lambda r: (r["month"], r["date"] or r["month"]), reverse=True)
    total_out = sum((r["amount"] for r in results if r["kind"] == "expense"), ZERO)
    total_in = sum((r["amount"] for r in results if r["kind"] == "income"), ZERO)
    return {
        "results": results[:limit],
        "count": len(results),
        "total_expenses": total_out,
        "total_incomes": total_in,
    }


# ---------------------------------------------------------------- ritmo por categoria


def pace(db: Session, user: User, month: date, today: date | None = None) -> list[dict[str, Any]]:
    """Gasto de cada categoria comparado com o ritmo esperado até hoje.

    Referência: o limite da categoria ou, sem limite, a média dos 3 meses anteriores.
    """
    today = today or date.today()
    start, end = cycle_range(month, user.month_start_day)
    if today > end:
        elapsed = 1.0
    elif today < start:
        elapsed = 0.0
    else:
        elapsed = ((today - start).days + 1) / ((end - start).days + 1)
    categories = {c.id: c for c in db.scalars(select(Category).where(Category.user_id == user.id))}
    spent: dict[uuid.UUID | None, Decimal] = defaultdict(lambda: ZERO)
    for e in db.scalars(select(Expense).where(Expense.user_id == user.id, Expense.month == month)):
        spent[e.category_id] += e.amount
    past: dict[uuid.UUID | None, Decimal] = defaultdict(lambda: ZERO)
    for e in db.scalars(
        select(Expense).where(
            Expense.user_id == user.id,
            Expense.month >= add_months(month, -3),
            Expense.month < month,
        )
    ):
        past[e.category_id] += e.amount

    from app.services import limits

    month_limits = limits.for_month(db, user, month, categories)
    rows = []
    for category_id in set(spent) | {c for c, cat in categories.items() if cat.monthly_limit}:
        category = categories.get(category_id) if category_id else None
        found = month_limits.get(category_id) if category_id else None
        limit = found.total if found else None
        reference = limit or (past[category_id] / 3).quantize(Decimal("0.01"))
        value = spent[category_id]
        if reference <= 0:
            continue
        expected = (reference * Decimal(str(round(elapsed, 4)))).quantize(Decimal("0.01"))
        if value >= reference:
            status = "over"
        elif expected > 0 and value > expected * Decimal("1.1"):
            status = "risk"
        else:
            status = "ok"
        rows.append(
            {
                "category_id": category_id,
                "name": category.name if category else "Sem categoria",
                "spent": value,
                "reference": reference,
                "reference_kind": "limit" if limit else "average",
                "expected_now": expected,
                "pct": round(float(value / reference * 100), 1),
                "status": status,
            }
        )
    order = {"over": 0, "risk": 1, "ok": 2}
    rows.sort(key=lambda r: (order[r["status"]], -r["pct"]))
    return rows


# ---------------------------------------------------------------- copiar mês anterior


def copy_candidates(db: Session, user: User, month: date) -> list[Expense]:
    """Despesas avulsas do mês anterior (as fixas e parcelas já se lançam sozinhas)."""
    previous = add_months(month, -1)
    return list(
        db.scalars(
            select(Expense)
            .where(
                Expense.user_id == user.id,
                Expense.month == previous,
                Expense.recurring_id.is_(None),
                Expense.installment_group_id.is_(None),
                Expense.card_id.is_(None),
            )
            .order_by(Expense.due_date, Expense.created_at)
        )
    )


def copy_previous(db: Session, user: User, month: date, ids: list[uuid.UUID]) -> list[Expense]:
    budget.ensure_month(db, user, month)
    chosen = [e for e in copy_candidates(db, user, month) if e.id in set(ids)]
    created = []
    for e in chosen:
        copy = Expense(
            user_id=user.id,
            month=month,
            description=e.description,
            amount=e.amount,
            category_id=e.category_id,
            due_date=with_day(month, e.due_date.day) if e.due_date else None,
            payment_method=e.payment_method,
            notes=e.notes,
            account_id=e.account_id,
            paid=False,
        )
        db.add(copy)
        created.append(copy)
    db.commit()
    return created
