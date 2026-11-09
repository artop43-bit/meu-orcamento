"""Análises: score financeiro, regra 50/30/20, comparação entre meses e projeção."""

import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.months import add_months
from app.models import BudgetMonth, Expense, Income, User
from app.services import budget, investments, planned

ZERO = Decimal("0.00")
RESERVE_TARGET_MONTHS = 6
CONSISTENCY_WINDOW = 6

SCORE_LABELS = [(80, "Excelente"), (60, "Boa"), (40, "Regular"), (20, "Atenção"), (0, "Crítica")]


def _f(value: Decimal) -> float:
    return float(value)


def _pct(part: Decimal, whole: Decimal) -> float | None:
    return None if whole <= 0 else round(_f(part / whole * 100), 1)


# ---------------------------------------------------------------- score


def average_expenses(history: list[dict[str, Any]], fallback: Decimal) -> Decimal:
    """Média de gastos dos últimos 3 meses com lançamentos (base para a reserva)."""
    recent = [p["expenses"] for p in history if p["has_data"] and p["expenses"] > 0][-3:]
    if not recent:
        return fallback
    return sum(recent, ZERO) / len(recent)


def score(db: Session, user: User, month: date) -> dict[str, Any]:
    summary = budget.get_month(db, user, month).summary
    income: Decimal = summary["income_total"]
    expenses: Decimal = summary["expense_total"]
    balance: Decimal = summary["balance"]

    if income <= 0 and expenses <= 0:
        return {
            "score": None,
            "label": "Sem dados",
            "components": [],
            "tips": ["Lance sua renda e suas contas deste mês para calcular o score."],
            "reserve_total": ZERO,
            "reserve_months": None,
        }

    history = budget.history(db, user, month, CONSISTENCY_WINDOW)
    components = []
    tips = []

    # 1. Saldo do mês (30): positivo vale tudo; um déficit de 50% da renda zera.
    if income > 0:
        ratio = _f(balance / income)
        points = 30.0 if ratio >= 0 else max(0.0, 30 * (1 + ratio / 0.5))
    else:
        points = 30.0 if balance >= 0 else 0.0
    components.append(
        {
            "key": "balance",
            "label": "Saldo do mês",
            "points": points,
            "max": 30,
            "detail": "Renda maior que as contas" if balance >= 0 else "Contas maiores que a renda",
        }
    )
    if balance < 0:
        tips.append(
            "Suas contas superam a renda. "
            "Priorize cortar gastos não essenciais ou renegociar dívidas."
        )

    # 2. Comprometimento (30): até 50% da renda vale tudo; 100% ou mais zera.
    committed = summary["committed_pct"] if summary["committed_pct"] is not None else 100.0
    if committed <= 50:
        points = 30.0
    elif committed >= 100:
        points = 0.0
    else:
        points = 30 * (1 - (committed - 50) / 50)
    components.append(
        {
            "key": "committed",
            "label": "Renda comprometida",
            "points": points,
            "max": 30,
            "detail": f"{committed:.1f}% da renda vai para contas".replace(".", ","),
        }
    )
    if committed > 70 and balance >= 0:
        tips.append(
            f"{committed:.0f}% da receita está comprometida: margem reduzida para imprevistos."
        )

    # 3. Reserva de emergência (25): 6 meses de gastos guardados vale tudo.
    reserve = investments.emergency_reserve_total(db, user)
    average = average_expenses(history, expenses)
    if average > 0:
        reserve_months = _f(reserve / average)
        points = min(25.0, reserve_months / RESERVE_TARGET_MONTHS * 25)
    else:
        reserve_months = None
        points = 25.0 if reserve > 0 else 0.0
    components.append(
        {
            "key": "reserve",
            "label": "Reserva de emergência",
            "points": points,
            "max": 25,
            "detail": (
                f"Cobre {reserve_months:.1f} meses de gastos".replace(".", ",")
                if reserve_months is not None
                else "Sem gastos para comparar"
            ),
        }
    )
    if reserve <= 0:
        tips.append(
            "Cadastre seus investimentos de reserva de emergência (em Investimentos) "
            "para que contem no score."
        )
    elif reserve_months is not None and reserve_months < 3:
        tips.append("A reserva cobre menos de 3 meses de despesas; a referência é de 3 a 6.")

    # 4. Consistência (15): meses recentes fechados no positivo.
    months_with_data = [p for p in history if p["has_data"]]
    positive = sum(1 for p in months_with_data if p["balance"] >= 0)
    ratio = positive / len(months_with_data) if months_with_data else 0.0
    components.append(
        {
            "key": "consistency",
            "label": "Consistência",
            "points": 15 * ratio,
            "max": 15,
            "detail": f"{positive} de {len(months_with_data)} meses recentes no positivo",
        }
    )
    if months_with_data and ratio < 0.5:
        tips.append("Mais da metade dos últimos meses teve resultado negativo.")

    total = round(max(0.0, min(100.0, sum(c["points"] for c in components))))
    for component in components:
        component["points"] = round(component["points"], 1)
    label = next(name for threshold, name in SCORE_LABELS if total >= threshold)
    if not tips:
        tips.append("Indicadores equilibrados no período.")

    return {
        "score": total,
        "label": label,
        "components": components,
        "tips": tips[:3],
        "reserve_total": reserve,
        "reserve_months": round(reserve_months, 1) if reserve_months is not None else None,
    }


# ---------------------------------------------------------------- 50/30/20


def rule_50_30_20(db: Session, user: User, month: date) -> dict[str, Any]:
    summary = budget.get_month(db, user, month).summary
    income: Decimal = summary["income_total"]
    needs: Decimal = summary["essential_total"]
    wants: Decimal = summary["non_essential_total"]
    savings = max(ZERO, summary["balance"])
    deficit = max(ZERO, needs + wants - income)

    needs_pct, wants_pct, savings_pct = (_pct(v, income) for v in (needs, wants, savings))
    return {
        "income": income,
        "needs": needs,
        "wants": wants,
        "savings": savings,
        "deficit": deficit,
        "needs_pct": needs_pct,
        "wants_pct": wants_pct,
        "savings_pct": savings_pct,
        "needs_ok": needs_pct is not None and needs_pct <= 50,
        "wants_ok": wants_pct is not None and wants_pct <= 30,
        "savings_ok": savings_pct is not None and savings_pct >= 20,
    }


# ---------------------------------------------------------------- comparação


def compare(db: Session, user: User, month_a: date, month_b: date) -> dict[str, Any]:
    a = budget.get_month(db, user, month_a).summary
    b = budget.get_month(db, user, month_b).summary

    rows: dict[uuid.UUID | None, dict[str, Any]] = {}
    for side, summary in (("a", a), ("b", b)):
        for item in summary["by_category"]:
            row = rows.setdefault(
                item["category_id"],
                {"category_id": item["category_id"], "name": item["name"], "a": ZERO, "b": ZERO},
            )
            row[side] = item["total"]

    categories = []
    for row in rows.values():
        row["delta"] = row["b"] - row["a"]
        row["delta_pct"] = _pct(row["delta"], row["a"]) if row["a"] > 0 else None
        categories.append(row)
    categories.sort(key=lambda r: abs(r["delta"]), reverse=True)

    def totals(key: str) -> dict[str, Any]:
        return {"a": a[key], "b": b[key], "delta": b[key] - a[key]}

    return {
        "income": totals("income_total"),
        "expenses": totals("expense_total"),
        "balance": totals("balance"),
        "categories": categories,
    }


# ---------------------------------------------------------------- projeção


def projection(db: Session, user: User, start: date, months: int) -> list[dict[str, Any]]:
    """Próximos meses com base no que já existe (parcelas, lançamentos) e nas fixas.

    Meses já abertos usam só os lançamentos reais (as fixas já foram lançadas neles).
    Meses ainda não abertos somam os lançamentos existentes às fixas ativas no período.
    Receitas recorrentes variáveis (freelance, comissões) entram pela média do que já foi recebido.
    Gastos planejados ainda não lançados entram no mês da data.
    """
    end = add_months(start, months - 1)

    def sums(model: type[Income] | type[Expense]) -> dict[date, Decimal]:
        stmt = (
            select(model.month, func.sum(model.amount))
            .where(model.user_id == user.id, model.month.between(start, end))
            .group_by(model.month)
        )
        return {month: Decimal(total) for month, total in db.execute(stmt)}

    incomes = sums(Income)
    expenses = sums(Expense)
    # v1.6: parte dos gastos que é parcela (compras parceladas, financiamentos): base do
    # "quanto da renda já está comprometida com parcelas" na calculadora de parcelamento.
    installments = {
        month: Decimal(total)
        for month, total in db.execute(
            select(Expense.month, func.sum(Expense.amount))
            .where(
                Expense.user_id == user.id,
                Expense.month.between(start, end),
                Expense.installment_total > 1,
            )
            .group_by(Expense.month)
        )
    }
    # Gastos não essenciais (categoria não essencial ou sem categoria), usados pelo simulador.
    essential_ids = {c.id for c in budget.list_categories(db, user) if c.is_essential}
    wants: dict[date, Decimal] = defaultdict(lambda: ZERO)
    for month, category_id, total in db.execute(
        select(Expense.month, Expense.category_id, func.sum(Expense.amount))
        .where(Expense.user_id == user.id, Expense.month.between(start, end))
        .group_by(Expense.month, Expense.category_id)
    ):
        if category_id not in essential_ids:
            wants[month] += Decimal(total)
    opened = set(
        db.scalars(
            select(BudgetMonth.month).where(
                BudgetMonth.user_id == user.id, BudgetMonth.month.between(start, end)
            )
        )
    )
    recurring = budget.list_recurring(db, user)
    variable_avg = _variable_income_average(db, user, recurring, start)
    planned_by_month: dict[date, Decimal] = defaultdict(lambda: ZERO)
    planned_wants: dict[date, Decimal] = defaultdict(lambda: ZERO)
    for item in planned.pending_planned(db, user, start, planned.month_end(end)):
        key = item.date.replace(day=1)
        planned_by_month[key] += item.amount
        if item.category_id not in essential_ids:
            planned_wants[key] += item.amount

    points = []
    cumulative = ZERO
    for index in range(months):
        month = add_months(start, index)
        income = incomes.get(month, ZERO)
        expense = expenses.get(month, ZERO)
        non_essential = wants[month]
        if month not in opened:
            for item in recurring:
                if not budget.active_in(item, month):
                    continue
                if item.kind == "income":
                    income += variable_avg.get(item.id, item.amount)
                else:
                    expense += item.amount
                    if item.category_id not in essential_ids:
                        non_essential += item.amount
        expense += planned_by_month[month]
        non_essential += planned_wants[month]
        balance = income - expense
        cumulative += balance
        points.append(
            {
                "month": month,
                "income": income,
                "expenses": expense,
                "planned": planned_by_month[month],
                "installments": installments.get(month, ZERO),
                "non_essential": non_essential,
                "balance": balance,
                "cumulative": cumulative,
            }
        )
    return points


def _variable_income_average(
    db: Session, user: User, recurring: list[Any], before: date
) -> dict[uuid.UUID, Decimal]:
    """Média dos últimos recebimentos de cada renda fixa variável (até 6 meses)."""
    result: dict[uuid.UUID, Decimal] = {}
    for item in recurring:
        if item.kind != "income" or item.income_type != "variable":
            continue
        amounts = list(
            db.scalars(
                select(Income.amount)
                .where(
                    Income.recurring_id == item.id,
                    Income.month < before,
                    Income.month >= add_months(before, -CONSISTENCY_WINDOW),
                )
                .order_by(Income.month.desc())
            )
        )
        if amounts:
            result[item.id] = (sum(amounts, ZERO) / len(amounts)).quantize(Decimal("0.01"))
    return result
