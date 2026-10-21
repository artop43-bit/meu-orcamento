"""Regras do orçamento: categorias, meses, rendas, contas, parcelas, fixas, metas e histórico.

Toda consulta filtra por usuário; acessar item de outra pessoa responde "não encontrado".
"""

import calendar
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_DOWN, Decimal
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.months import add_months, current_month, cycle_date, parse_month, with_day
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
    ("Compras", False, "#ff9da7"),
    ("Assinaturas", False, "#8cd17d"),
    ("Pets", False, "#d4a6c8"),
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


def _carry_changes(category: Category | None, user: User, changes: dict[str, Any]) -> None:
    """Ligar a sobra marca o mês atual como início do acúmulo; desligar zera."""
    if "carry_over" not in changes or changes["carry_over"] is None:
        changes.pop("carry_over", None)
        return
    if changes["carry_over"] and not (category and category.carry_over):
        changes["carry_since"] = current_month(user.month_start_day)
    elif not changes["carry_over"]:
        changes["carry_since"] = None


def create_category(db: Session, user: User, data: dict[str, Any]) -> Category:
    _ensure_unique_category_name(db, user, data["name"])
    _carry_changes(None, user, data)
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
    _carry_changes(category, user, changes)
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


def _start_day(db: Session, user_id: uuid.UUID) -> int:
    user = db.get(User, user_id)
    return user.month_start_day if user else 1


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
                income_type=item.income_type or "fixed",
                day=item.due_day,
                notes=item.notes,
                recurring_id=item.id,
                account_id=item.account_id,
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
                due_date=cycle_date(month, item.due_day, _start_day(db, item.user_id))
                if item.due_day
                else None,
                payment_method=item.payment_method,
                notes=item.notes,
                recurring_id=item.id,
            )
        )


def _months_between(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + end.month - start.month


def active_in(item: RecurringItem, month: date) -> bool:
    """A fixa cai neste mês? Respeita o período e a frequência (a cada N meses)."""
    if month < item.start_month or (item.end_month is not None and month > item.end_month):
        return False
    return _months_between(item.start_month, month) % (item.interval_months or 1) == 0


def _materialize_opened(db: Session, user: User, item: RecurringItem, since: date) -> None:
    """Lança a fixa nos meses já abertos a partir de `since`."""
    for (month,) in db.execute(
        select(BudgetMonth.month).where(BudgetMonth.user_id == user.id, BudgetMonth.month >= since)
    ):
        if active_in(item, month):
            _materialize(db, item, month)
    # A sessão não faz flush sozinha: sem isto, o lançamento do mês aberto seria criado duas vezes.
    db.flush()


def ensure_month(db: Session, user: User, month: date) -> None:
    """Na primeira vez que um mês é aberto, lança nele as contas e rendas fixas."""
    exists = db.scalar(
        select(BudgetMonth.id).where(BudgetMonth.user_id == user.id, BudgetMonth.month == month)
    )
    if exists is not None:
        return
    db.add(BudgetMonth(user_id=user.id, month=month))
    for item in db.scalars(select(RecurringItem).where(RecurringItem.user_id == user.id)):
        if active_in(item, month):
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
        data["payment_method"] = None
        data["income_type"] = data.get("income_type") or "fixed"
    else:
        data["income_type"] = None
    _check_category(db, user, data.get("category_id"))

    item = RecurringItem(user_id=user.id, start_month=start, end_month=end, **data)
    db.add(item)
    db.flush()
    # Meses já abertos dentro do período recebem o lançamento na hora.
    _materialize_opened(db, user, item, start)
    db.commit()
    return item


def update_recurring(
    db: Session,
    user: User,
    item_id: uuid.UUID,
    changes: dict[str, Any],
    from_month: date | None = None,
) -> RecurringItem:
    """Altera a fixa e os lançamentos não pagos a partir de `from_month` (padrão: mês atual)."""
    item = _owned(db, RecurringItem, item_id, user)
    if "end_month" in changes:
        changes["end_month"] = parse_month(changes["end_month"]) if changes["end_month"] else None
        _validate_period(item.start_month, changes["end_month"])
    if item.kind == "income":
        changes.pop("category_id", None)
        changes.pop("payment_method", None)
    else:
        changes.pop("income_type", None)
    _check_category(db, user, changes.get("category_id"))
    _apply(item, changes)

    # Propaga para os lançamentos a partir do mês escolhido que ainda não foram pagos.
    this_month = from_month or current_month(user.month_start_day)
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
        if not active_in(item, instance.month):
            db.delete(instance)
            continue
        instance.description = item.description
        instance.amount = item.amount
        instance.notes = item.notes
        if isinstance(instance, Expense):
            instance.category_id = item.category_id
            instance.payment_method = item.payment_method
            instance.due_date = (
                cycle_date(instance.month, item.due_day, user.month_start_day)
                if item.due_day
                else None
            )
        else:
            instance.income_type = item.income_type or "fixed"
            instance.day = item.due_day
    db.flush()
    # Meses já abertos que passaram a ter o lançamento (ex.: mudou a frequência).
    _materialize_opened(db, user, item, this_month)
    db.commit()
    return item


def delete_recurring(db: Session, user: User, item_id: uuid.UUID) -> None:
    """Remove a fixa e os lançamentos futuros; mantém o mês atual e os anteriores."""
    item = _owned(db, RecurringItem, item_id, user)
    after = current_month(user.month_start_day)
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


def _check_account(db: Session, user: User, account_id: uuid.UUID | None) -> None:
    if account_id is not None:
        from app.models import MoneyAccount

        _owned(db, MoneyAccount, account_id, user)


def _check_benefit(
    db: Session, user: User, account_id: uuid.UUID | None, category_id: uuid.UUID | None
) -> None:
    """Vale-refeição/alimentação (v1.4) só paga a categoria escolhida na conta."""
    if account_id is None:
        return
    from app.models import MoneyAccount

    account = db.get(MoneyAccount, account_id)
    if account is None or account.kind != "benefit" or account.benefit_category_id is None:
        return
    if category_id != account.benefit_category_id:
        category = db.get(Category, account.benefit_category_id)
        name = category.name if category else "a categoria do vale"
        raise AppError(
            400,
            "benefit_category",
            f"{account.name} só paga despesas de {name}. Escolha essa categoria ou outra conta.",
        )


MONTH_NAMES = (
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)


def check_day_in_month(day: int | None, month: date) -> None:
    """Lançamento só deste mês: o dia precisa existir no mês (31/02 não existe).

    Nos lançamentos que se repetem vale 1 a 31: nos meses mais curtos cai no último dia.
    """
    if day is None:
        return
    last = calendar.monthrange(month.year, month.month)[1]
    if day > last:
        raise AppError(
            400,
            "invalid_day",
            f"{MONTH_NAMES[month.month - 1].capitalize()} de {month.year} tem {last} dias. "
            f"Informe um dia entre 1 e {last}.",
        )


def create_income(db: Session, user: User, month: date, data: dict[str, Any]) -> Income:
    """Lança a renda. Com repetição, cria uma fixa a partir deste mês e devolve a deste mês."""
    client_ref = data.pop("client_ref", None)
    if client_ref:
        ref = f"app:{client_ref.lower()}"
        existing = db.scalar(
            select(Income).where(Income.user_id == user.id, Income.import_ref == ref)
        )
        if existing is not None:
            return existing
        income = create_income(db, user, month, data)
        income.import_ref = ref
        db.commit()
        return income
    _check_account(db, user, data.get("account_id"))
    account_id = data.pop("account_id", None)
    repeat = data.pop("repeat", "once")
    until = data.pop("until_month", None)
    if repeat == "once":
        check_day_in_month(data.get("day"), month)
        income = Income(user_id=user.id, month=month, account_id=account_id, **data)
        db.add(income)
        db.commit()
        return income

    end = parse_month(until) if repeat == "period" and until else None
    if repeat == "period" and end is None:
        raise AppError(400, "invalid_period", "Informe até que mês a renda se repete.")
    _validate_period(month, end)
    item = RecurringItem(
        user_id=user.id,
        kind="income",
        description=data["description"],
        amount=data["amount"],
        income_type=data.get("income_type") or "fixed",
        due_day=data.get("day"),
        notes=data.get("notes"),
        start_month=month,
        end_month=end,
    )
    db.add(item)
    db.flush()
    _materialize_opened(db, user, item, month)
    _materialize(db, item, month)
    db.flush()
    income = db.scalar(select(Income).where(Income.recurring_id == item.id, Income.month == month))
    assert income is not None
    income.account_id = account_id
    db.commit()
    return income


# Campos do lançamento que também existem na fixa (nome no lançamento → nome na fixa).
_INCOME_TO_RECURRING = {
    "description": "description",
    "amount": "amount",
    "income_type": "income_type",
    "day": "due_day",
    "notes": "notes",
}
_EXPENSE_TO_RECURRING = {
    "description": "description",
    "amount": "amount",
    "category_id": "category_id",
    "notes": "notes",
    "payment_method": "payment_method",
}


def update_income(
    db: Session, user: User, income_id: uuid.UUID, changes: dict[str, Any], scope: str = "one"
) -> Income:
    """Altera a renda. Com scope="following", vale também para os próximos meses da fixa."""
    income = _owned(db, Income, income_id, user)
    _check_account(db, user, changes.get("account_id"))
    if scope == "following" and income.recurring_id is not None:
        if "account_id" in changes:
            income.account_id = changes.pop("account_id")
        recurring = {_INCOME_TO_RECURRING[k]: v for k, v in changes.items()}
        update_recurring(db, user, income.recurring_id, recurring, from_month=income.month)
        db.refresh(income)
        return income
    if income.recurring_id is None and "day" in changes:
        check_day_in_month(changes["day"], income.month)
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
    """Cria a conta (ou as parcelas, ou as partes de uma compra dividida em categorias)."""
    client_ref = data.pop("client_ref", None)
    ref = f"app:{client_ref.lower()}" if client_ref else None
    if ref:
        # Lançamento feito sem internet e reenviado: devolve o que já entrou, sem duplicar.
        existing = list(
            db.scalars(
                select(Expense)
                .where(Expense.user_id == user.id, Expense.import_ref == ref)
                .order_by(Expense.month, Expense.created_at)
            )
        )
        if existing:
            return existing
    parts = data.pop("parts", None)
    if parts:
        created = _create_split(db, user, month, data, parts)
    else:
        created = _create_expense(db, user, month, data)
    if ref:
        for expense in created:
            expense.import_ref = ref
        db.commit()
    return created


def _create_split(
    db: Session, user: User, month: date, data: dict[str, Any], parts: list[dict[str, Any]]
) -> list[Expense]:
    """Uma compra, várias categorias: cada parte vira uma conta com o seu valor (sem duplicar)."""
    if data.get("installments") or data.get("repeat"):
        raise AppError(
            400,
            "split_single",
            "A divisão em categorias vale para compras sem parcelas e sem repetição.",
        )
    total = sum((Decimal(p["amount"]) for p in parts), Decimal("0"))
    if total != data["amount"]:
        raise AppError(
            400,
            "split_sum",
            f"A soma das partes (R$ {_brl(total)}) precisa ser igual ao total "
            f"(R$ {_brl(data['amount'])}).",
        )
    for part in parts:
        _check_category(db, user, part["category_id"])
    group = uuid.uuid4()
    created: list[Expense] = []
    for part in parts:
        values = {**data, "amount": part["amount"], "category_id": part["category_id"]}
        rows = _create_expense(db, user, month, values)
        for row in rows:
            row.split_group_id = group
        created.extend(rows)
    db.commit()
    return created


def _brl(value: Decimal) -> str:
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _create_expense(db: Session, user: User, month: date, data: dict[str, Any]) -> list[Expense]:
    installments = data.pop("installments", None)
    paid = data.pop("paid", False)
    amount_mode = data.pop("amount_mode", "parcel")
    repeat = data.pop("repeat", False)
    interval = data.pop("interval_months", 1)
    until = data.pop("until_month", None)
    card_id = data.pop("card_id", None)
    purchase_date = data.pop("purchase_date", None)
    debit_card_id = data.pop("debit_card_id", None)
    if card_id is not None and debit_card_id is not None:
        raise AppError(400, "card_conflict", "Escolha crédito ou débito, não os dois.")
    if card_id is not None and data.get("payment_method") not in (None, "credit"):
        raise AppError(400, "card_needs_credit", "Compra no cartão de crédito usa a forma Crédito.")
    if debit_card_id is not None:
        from app.services import cards

        debit_card = cards.get_debit_card(db, user, debit_card_id)
        if installments:
            raise AppError(400, "debit_no_installments", "Compra no débito não pode ser parcelada.")
        # No débito o dinheiro sai na hora: entra paga, no dia da compra, da conta do cartão.
        data["payment_method"] = "debit"
        data["debit_card_id"] = debit_card.id
        if data.get("account_id") is None:
            data["account_id"] = debit_card.account_id
        if data.get("due_date") is None:
            data["due_date"] = purchase_date or date.today()
        paid = True
    _check_account(db, user, data.get("account_id"))
    if data.get("category_id") is None:
        # Regra automática do usuário ("contém uber → Transporte").
        from app.services import rules

        data["category_id"] = rules.matcher(db, user)(data["description"])
    _check_category(db, user, data.get("category_id"))
    _check_benefit(db, user, data.get("account_id"), data.get("category_id"))

    if card_id is not None:
        return _create_card_expense(
            db, user, data, card_id, purchase_date, installments, amount_mode, paid
        )

    if repeat and not installments:
        end = parse_month(until) if until else None
        _validate_period(month, end)
        due = data.get("due_date")
        item = RecurringItem(
            user_id=user.id,
            kind="expense",
            description=data["description"],
            amount=data["amount"],
            category_id=data.get("category_id"),
            due_day=due.day if due else None,
            payment_method=data.get("payment_method"),
            notes=data.get("notes"),
            start_month=month,
            end_month=end,
            interval_months=interval,
        )
        db.add(item)
        db.flush()
        _materialize_opened(db, user, item, month)
        _materialize(db, item, month)
        db.flush()
        expense = db.scalar(
            select(Expense).where(Expense.recurring_id == item.id, Expense.month == month)
        )
        assert expense is not None
        expense.account_id = data.get("account_id")
        expense.debit_card_id = data.get("debit_card_id")
        if paid:
            expense.paid = True
            expense.paid_at = utcnow()
        db.commit()
        return [expense]

    if not installments:
        expense = Expense(
            user_id=user.id, month=month, paid=paid, paid_at=utcnow() if paid else None, **data
        )
        db.add(expense)
        db.commit()
        return [expense]

    group = uuid.uuid4()
    due = data.pop("due_date", None)
    value = data.pop("amount")
    if amount_mode == "total":
        # Divide o total; os centavos que sobram vão para a 1ª parcela.
        parcel = (value / installments).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        if parcel <= 0:
            raise AppError(400, "invalid_amount", "O total é pequeno demais para tantas parcelas.")
        amounts = [value - parcel * (installments - 1)] + [parcel] * (installments - 1)
    else:
        amounts = [value] * installments
    created = []
    for index in range(installments):
        installment_month = add_months(month, index)
        expense = Expense(
            amount=amounts[index],
            user_id=user.id,
            month=installment_month,
            due_date=with_day(installment_month, due.day) if due else None,
            installment_group_id=group,
            installment_number=index + 1,
            installment_total=installments,
            paid=paid and index == 0,
            paid_at=utcnow() if paid and index == 0 else None,
            **data,
        )
        db.add(expense)
        created.append(expense)
    db.commit()
    return created


def _split_amount(value: Decimal, count: int, mode: str) -> list[Decimal]:
    if mode != "total" or count <= 1:
        return [value] * count
    parcel = (value / count).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    if parcel <= 0:
        raise AppError(400, "invalid_amount", "O total é pequeno demais para tantas parcelas.")
    return [value - parcel * (count - 1)] + [parcel] * (count - 1)


def _create_card_expense(
    db: Session,
    user: User,
    data: dict[str, Any],
    card_id: uuid.UUID,
    purchase_date: date | None,
    installments: int | None,
    amount_mode: str,
    paid: bool,
) -> list[Expense]:
    """Compra no cartão: cada parcela vai para o mês da fatura em que cai."""
    from app.services import cards

    card = cards.get_credit_card(db, user, card_id)
    purchase = purchase_date or data.pop("due_date", None) or date.today()
    data.pop("due_date", None)
    count = installments or 1
    amounts = _split_amount(data.pop("amount"), count, amount_mode)
    group = uuid.uuid4() if count > 1 else None
    data["payment_method"] = "credit"
    created = []
    for index, due in enumerate(cards.installment_dates(card, purchase, count)):
        month = due.replace(day=1)
        ensure_month(db, user, month)
        expense = Expense(
            user_id=user.id,
            month=month,
            amount=amounts[index],
            due_date=due,
            card_id=card.id,
            purchase_date=purchase,
            installment_group_id=group,
            installment_number=index + 1 if group else None,
            installment_total=count if group else None,
            paid=paid and index == 0,
            paid_at=utcnow() if paid and index == 0 else None,
            **data,
        )
        db.add(expense)
        created.append(expense)
    db.commit()
    return created


BULK_ACTIONS = ("pay", "unpay", "delete", "category")


def bulk_expenses(
    db: Session,
    user: User,
    ids: list[uuid.UUID],
    action: str,
    category_id: uuid.UUID | None = None,
) -> int:
    """Mesma ação em várias contas de uma vez (só as do próprio usuário)."""
    if action == "category":
        _check_category(db, user, category_id)
    items = list(db.scalars(select(Expense).where(Expense.user_id == user.id, Expense.id.in_(ids))))
    now = utcnow()
    for expense in items:
        if action == "pay" and not expense.paid:
            expense.paid, expense.paid_at = True, now
        elif action == "unpay" and expense.paid:
            expense.paid, expense.paid_at = False, None
        elif action == "category":
            expense.category_id = category_id
        elif action == "delete":
            db.delete(expense)
    db.commit()
    return len(items)


def update_expense(
    db: Session, user: User, expense_id: uuid.UUID, changes: dict[str, Any], scope: str = "one"
) -> Expense:
    """Altera a conta. Com scope="following", vale também para as próximas parcelas ou meses."""
    expense = _owned(db, Expense, expense_id, user)
    if "category_id" in changes:
        _check_category(db, user, changes["category_id"])
    _check_account(db, user, changes.get("account_id"))
    _check_benefit(
        db,
        user,
        changes["account_id"] if "account_id" in changes else expense.account_id,
        changes["category_id"] if "category_id" in changes else expense.category_id,
    )
    shared = {k: v for k, v in changes.items() if k in _EXPENSE_TO_RECURRING}
    if scope == "following" and shared:
        if expense.installment_group_id is not None:
            for other in db.scalars(
                select(Expense).where(
                    Expense.user_id == user.id,
                    Expense.installment_group_id == expense.installment_group_id,
                    Expense.installment_number > (expense.installment_number or 1),
                    Expense.paid.is_(False),
                )
            ):
                _apply(other, shared)
        elif expense.recurring_id is not None:
            update_recurring(db, user, expense.recurring_id, dict(shared), from_month=expense.month)
            db.refresh(expense)
    if "paid" in changes and changes["paid"] is not None and changes["paid"] != expense.paid:
        expense.paid_at = utcnow() if changes["paid"] else None
        if expense.split_group_id is not None:
            # Compra dividida: pagar uma parte paga a compra inteira.
            for other in db.scalars(
                select(Expense).where(
                    Expense.user_id == user.id,
                    Expense.split_group_id == expense.split_group_id,
                    Expense.id != expense.id,
                )
            ):
                other.paid, other.paid_at = changes["paid"], expense.paid_at
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

    from app.services import limits

    month_limits = limits.for_month(db, user, month, categories)
    essential_total = ZERO
    category_totals = []
    for category_id, total in by_category.items():
        category = categories.get(category_id) if category_id else None
        essential = bool(category and category.is_essential)
        if essential:
            essential_total += total
        limit = month_limits.get(category_id) if category_id else None
        category_totals.append(
            {
                "category_id": category_id,
                "name": category.name if category else "Sem categoria",
                "is_essential": essential,
                "total": total,
                "limit": limit.total if limit else None,
                "limit_pct": _pct(total, limit.total) if limit else None,
                "limit_carried": limit.carried if limit and limit.carried else None,
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
