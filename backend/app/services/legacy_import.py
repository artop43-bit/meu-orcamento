"""Importação do arquivo .json exportado pelo app antigo (meu-orcamento.html).

Fluxo em duas etapas: `preview` lê o arquivo e devolve os itens normalizados para o
usuário revisar (marcar o que é fixo, desmarcar o que não quer); `commit` grava o que
foi confirmado, tudo numa única transação.

O perfil do arquivo antigo (nome, idade, foto) é ignorado de propósito.
"""

import re
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.months import add_months, format_month, parse_month, with_day
from app.core.parsing import normalize_text, parse_amount, parse_date
from app.db.types import utcnow
from app.models import BudgetMonth, Category, Expense, Goal, Income, Investment, RecurringItem, User
from app.services import budget

LEGACY_PREFIX = "legacy:"

# Categorias do app antigo -> nome no app novo (e se é essencial, caso precise criar).
CATEGORY_MAP: dict[str, tuple[str, bool]] = {
    "moradia": ("Moradia", True),
    "alimentacao": ("Alimentação", True),
    "transporte": ("Transporte", True),
    "saude": ("Saúde", True),
    "educacao": ("Educação", True),
    "servicos": ("Serviços", True),
    "lazer": ("Lazer", False),
    "outros": ("Outros", False),
    "essencial": ("Outros essenciais", True),
    "nao-essencial": ("Outros", False),
    "nao_essencial": ("Outros", False),
}


def _text(value: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _due_day(value: Any) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.isdigit() and 1 <= int(text) <= 31:
        return int(text)
    parsed = parse_date(text)
    return parsed.day if parsed else None


def _history_month(key: Any) -> date | None:
    """O app antigo guardava o mês começando em 0: "2026-6" é julho de 2026."""
    match = re.match(r"^(\d{4})-(\d{1,2})$", str(key or ""))
    if not match:
        return None
    month_index = int(match[2])
    if not 0 <= month_index <= 11:
        return None
    return date(int(match[1]), month_index + 1, 1)


def preview(db: Session, user: User, data: Any, month: date) -> dict[str, Any]:
    if not isinstance(data, dict) or not ("bills" in data or "incomes" in data):
        raise AppError(
            400,
            "invalid_file",
            "Este arquivo não parece ser um backup do app antigo (faltam rendas e contas).",
        )

    incomes = []
    for item in data.get("incomes") or []:
        if not isinstance(item, dict):
            continue
        amount = parse_amount(item.get("value"))
        description = _text(item.get("name"), 120)
        if amount is None or amount <= 0:
            continue
        # Renda costuma se repetir (salário, benefício): vem marcada como fixa.
        incomes.append({"description": description or "Renda", "amount": amount, "recurring": True})

    expenses = []
    for item in data.get("bills") or []:
        if not isinstance(item, dict):
            continue
        amount = parse_amount(item.get("value"))
        description = _text(item.get("name"), 120)
        if amount is None or amount <= 0:
            continue
        slug = normalize_text(str(item.get("category") or "outros")).replace(" ", "-")
        category_name = CATEGORY_MAP.get(slug, ("Outros", False))[0]

        installment = item.get("installment") if isinstance(item.get("installment"), dict) else {}
        current = total = None
        if installment.get("enabled"):
            try:
                current, total = int(installment.get("current")), int(installment.get("total"))
            except (TypeError, ValueError):
                current = total = None
            if not (current and total and 1 <= current <= total <= 120 and total >= 2):
                current = total = None

        expenses.append(
            {
                "description": description or "Conta",
                "amount": amount,
                "category_name": category_name,
                "due_day": _due_day(item.get("due")),
                "paid": bool(item.get("paid")),
                "notes": _text(item.get("notes"), 500) or None,
                "installment_current": current,
                "installment_total": total,
                "recurring": False,
            }
        )

    goals = []
    for item in data.get("goals") or []:
        if not isinstance(item, dict):
            continue
        target = parse_amount(item.get("target") or item.get("targetAmount"))
        if target is None or target <= 0:
            continue
        current = parse_amount(item.get("current") or item.get("saved")) or Decimal("0")
        goals.append(
            {
                "name": _text(item.get("name"), 80) or "Meta",
                "target_amount": target,
                "current_amount": max(Decimal("0"), current),
            }
        )

    history = []
    for item in data.get("history") or []:
        if not isinstance(item, dict):
            continue
        hist_month = _history_month(item.get("key"))
        if hist_month is None or hist_month == month:
            continue
        income = parse_amount(item.get("income")) or Decimal("0")
        spent = parse_amount(item.get("totalBills")) or Decimal("0")
        if income <= 0 and spent <= 0:
            continue
        history.append({"month": format_month(hist_month), "income": income, "expenses": spent})

    reserve = parse_amount(data.get("reserve"))
    already = db.scalar(
        select(func.count(Income.id)).where(
            Income.user_id == user.id, Income.import_ref.like(f"{LEGACY_PREFIX}%")
        )
    ) or db.scalar(
        select(func.count(Expense.id)).where(
            Expense.user_id == user.id, Expense.import_ref.like(f"{LEGACY_PREFIX}%")
        )
    )

    return {
        "month": format_month(month),
        "incomes": incomes,
        "expenses": expenses,
        "goals": goals,
        "history": history,
        "reserve": reserve if reserve and reserve > 0 else None,
        "already_imported": bool(already),
    }


def _category_for(
    db: Session, user: User, name: str | None, cache: dict[str, Category]
) -> Category | None:
    if not name:
        return None
    key = normalize_text(name)
    if key in cache:
        return cache[key]
    category = db.scalar(
        select(Category).where(
            Category.user_id == user.id, func.lower(Category.name) == name.lower()
        )
    )
    if category is None:
        essential = next((e for n, e in CATEGORY_MAP.values() if n == name), False)
        category = Category(user_id=user.id, name=name, is_essential=essential)
        db.add(category)
        db.flush()
    cache[key] = category
    return category


def commit(db: Session, user: User, payload: dict[str, Any]) -> dict[str, int]:
    month = parse_month(payload["month"])
    ref = f"{LEGACY_PREFIX}{format_month(month)}"
    opened = {
        m for (m,) in db.execute(select(BudgetMonth.month).where(BudgetMonth.user_id == user.id))
    }
    categories: dict[str, Category] = {}
    counts = {"incomes": 0, "expenses": 0, "goals": 0, "history_months": 0, "investments": 0}

    def add_recurring(**fields: Any) -> RecurringItem:
        item = RecurringItem(user_id=user.id, start_month=month, **fields)
        db.add(item)
        db.flush()
        # Lança já no mês importado (mesmo que ainda não aberto) e nos meses abertos depois dele.
        for target in {month} | {m for m in opened if m >= month}:
            budget._materialize(db, item, target)
        db.flush()
        return item

    for index, item in enumerate(payload.get("incomes", [])):
        if item["recurring"]:
            add_recurring(kind="income", description=item["description"], amount=item["amount"])
        else:
            db.add(
                Income(
                    user_id=user.id,
                    month=month,
                    description=item["description"],
                    amount=item["amount"],
                    import_ref=f"{ref}:income:{index}",
                )
            )
        counts["incomes"] += 1

    for index, item in enumerate(payload.get("expenses", [])):
        category = _category_for(db, user, item.get("category_name"), categories)
        category_id = category.id if category else None
        due_day = item.get("due_day")

        current, total = item.get("installment_current"), item.get("installment_total")
        if current and total and current <= total:
            group = uuid.uuid4()
            # Parcela atual neste mês; as seguintes nos próximos meses.
            for offset, number in enumerate(range(current, total + 1)):
                installment_month = add_months(month, offset)
                db.add(
                    Expense(
                        user_id=user.id,
                        month=installment_month,
                        description=item["description"],
                        amount=item["amount"],
                        category_id=category_id,
                        due_date=with_day(installment_month, due_day) if due_day else None,
                        paid=bool(item.get("paid")) and offset == 0,
                        paid_at=utcnow() if item.get("paid") and offset == 0 else None,
                        notes=item.get("notes"),
                        installment_group_id=group,
                        installment_number=number,
                        installment_total=total,
                        import_ref=f"{ref}:expense:{index}:{number}",
                    )
                )
        elif item["recurring"]:
            recurring = add_recurring(
                kind="expense",
                description=item["description"],
                amount=item["amount"],
                category_id=category_id,
                due_day=due_day,
            )
            if item.get("paid"):
                # Estava paga no app antigo: só o lançamento do mês importado fica pago.
                instance = db.scalar(
                    select(Expense).where(
                        Expense.recurring_id == recurring.id, Expense.month == month
                    )
                )
                if instance is not None:
                    instance.paid = True
                    instance.paid_at = utcnow()
        else:
            db.add(
                Expense(
                    user_id=user.id,
                    month=month,
                    description=item["description"],
                    amount=item["amount"],
                    category_id=category_id,
                    due_date=with_day(month, due_day) if due_day else None,
                    paid=bool(item.get("paid")),
                    paid_at=utcnow() if item.get("paid") else None,
                    notes=item.get("notes"),
                    import_ref=f"{ref}:expense:{index}",
                )
            )
        counts["expenses"] += 1

    for item in payload.get("goals", []):
        db.add(Goal(user_id=user.id, **item))
        counts["goals"] += 1

    # Histórico: um lançamento de renda e um de contas por mês, só em meses vazios.
    for item in payload.get("history", []):
        hist_month = parse_month(item["month"])
        has_data = db.scalar(
            select(func.count(Income.id)).where(
                Income.user_id == user.id, Income.month == hist_month
            )
        ) or db.scalar(
            select(func.count(Expense.id)).where(
                Expense.user_id == user.id, Expense.month == hist_month
            )
        )
        if has_data:
            continue
        if item["income"] > 0:
            db.add(
                Income(
                    user_id=user.id,
                    month=hist_month,
                    description="Renda (histórico importado)",
                    amount=item["income"],
                    import_ref=f"{LEGACY_PREFIX}history:{item['month']}:income",
                )
            )
        if item["expenses"] > 0:
            db.add(
                Expense(
                    user_id=user.id,
                    month=hist_month,
                    description="Contas (histórico importado)",
                    amount=item["expenses"],
                    paid=True,
                    paid_at=utcnow(),
                    import_ref=f"{LEGACY_PREFIX}history:{item['month']}:expenses",
                )
            )
        counts["history_months"] += 1

    if payload.get("reserve"):
        db.add(
            Investment(
                user_id=user.id,
                name="Reserva de emergência (importada)",
                kind="poupanca",
                invested_amount=payload["reserve"],
                current_value=payload["reserve"],
                is_emergency_reserve=True,
            )
        )
        counts["investments"] += 1

    db.commit()
    return counts
