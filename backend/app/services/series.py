"""Séries para o construtor "Monte sua análise".

Uma configuração (o quê, período, agrupamento, comparação) vira rótulos + séries de
números prontos para qualquer tipo de gráfico. A comparação é sempre feita sobre o
total de cada rótulo, num período equivalente (anterior, ano passado ou média).
"""

import json
import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.months import add_months, format_month, parse_month
from app.models import Expense, Income, SavedAnalysis, User
from app.services import budget, investments

ZERO = Decimal("0")
MAX_SAVED = 30

KIND_LABELS = {
    "poupanca": "Poupança",
    "renda_fixa": "Renda fixa",
    "tesouro": "Tesouro Direto",
    "fundos": "Fundos",
    "acoes": "Ações",
    "fiis": "Fundos imobiliários",
    "cripto": "Criptomoedas",
    "previdencia": "Previdência",
    "outro": "Outro",
}
TYPE_LABELS = {"essential": "Essencial", "non_essential": "Não essencial"}
TYPE_COLORS = {"essential": "#4e79a7", "non_essential": "#d97b29"}
METRIC_NAMES = {
    "expenses": "Gastos",
    "income": "Renda",
    "balance": "Sobra",
    "savings_rate": "Taxa de poupança",
    "investments": "Patrimônio",
}
COMPARE_NAMES = {
    "previous": "Período anterior",
    "last_year": "Mesmo período do ano passado",
    "average": "Sua média (12 meses antes)",
}


def months_between(start: date, end: date) -> list[date]:
    months = []
    current = start
    while current <= end:
        months.append(current)
        current = add_months(current, 1)
    return months


def _f(value: Decimal) -> float:
    return round(float(value), 2)


class _Data:
    """Totais por mês (e por categoria) num intervalo, consultados uma vez só."""

    def __init__(
        self, db: Session, user: User, start: date, end: date, categories: set[uuid.UUID] | None
    ):
        self.months = months_between(start, end)
        stmt = (
            select(Expense.month, Expense.category_id, func.sum(Expense.amount))
            .where(Expense.user_id == user.id, Expense.month.between(start, end))
            .group_by(Expense.month, Expense.category_id)
        )
        if categories:
            stmt = stmt.where(Expense.category_id.in_(categories))
        self.expenses: dict[date, dict[uuid.UUID | None, Decimal]] = defaultdict(dict)
        for month, category_id, total in db.execute(stmt):
            self.expenses[month][category_id] = Decimal(total)
        self.income: dict[date, Decimal] = {
            month: Decimal(total)
            for month, total in db.execute(
                select(Income.month, func.sum(Income.amount))
                .where(Income.user_id == user.id, Income.month.between(start, end))
                .group_by(Income.month)
            )
        }

    def expense_total(self, month: date) -> Decimal:
        return sum(self.expenses.get(month, {}).values(), ZERO)

    def metric(self, metric: str, month: date) -> float | None:
        income = self.income.get(month, ZERO)
        spent = self.expense_total(month)
        if metric == "expenses":
            return _f(spent)
        if metric == "income":
            return _f(income)
        if metric == "balance":
            return _f(income - spent)
        if metric == "savings_rate":
            return round(float((income - spent) / income * 100), 1) if income > 0 else None
        raise AppError(422, "invalid_metric", "Métrica inválida para este agrupamento.")

    def by_category(self) -> dict[uuid.UUID | None, Decimal]:
        totals: dict[uuid.UUID | None, Decimal] = defaultdict(lambda: ZERO)
        for per_category in self.expenses.values():
            for category_id, total in per_category.items():
                totals[category_id] += total
        return totals


def _period(config: dict[str, Any], today: date) -> tuple[date, date]:
    current = today.replace(day=1)
    period = config.get("period", "6m")
    if period == "custom":
        start, end = parse_month(config["start"]), parse_month(config["end"])
        if start > end:
            start, end = end, start
        if len(months_between(start, end)) > 60:
            raise AppError(422, "period_too_long", "Escolha um período de até 5 anos.")
        return start, end
    size = {"3m": 3, "6m": 6, "12m": 12, "24m": 24}[period]
    return add_months(current, -(size - 1)), current


def build(
    db: Session, user: User, config: dict[str, Any], today: date | None = None
) -> dict[str, Any]:
    today = today or date.today()
    metric = config["metric"]
    group = config["group"]
    compare = config.get("compare", "none")
    category_ids = {uuid.UUID(str(c)) for c in config.get("categories") or []} or None
    start, end = _period(config, today)
    categories = {c.id: c for c in budget.list_categories(db, user)}
    essential_ids = {cid for cid, c in categories.items() if c.is_essential}

    if metric == "investments":
        totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
        for item in investments.list_investments(db, user):
            totals[item.kind] += item.current_value
        keys = sorted(totals, key=lambda k: totals[k], reverse=True)
        values = [_f(totals[k]) for k in keys]
        return {
            "labels": [{"key": k, "label": KIND_LABELS.get(k, k)} for k in keys],
            "series": [
                {"key": "investments", "name": "Patrimônio", "color": None, "values": values}
            ],
            "compare": None,
            "unit": "money",
            "total": round(sum(values), 2),
            "compare_total": None,
            "start": format_month(start),
            "end": format_month(end),
        }

    if metric != "expenses" and group not in ("month",):
        raise AppError(422, "invalid_group", "Renda, sobra e poupança só podem ser vistas por mês.")
    unit = "percent" if metric == "savings_rate" else "money"

    def compute(first: date, last: date) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        data = _Data(db, user, first, last, category_ids)
        if group == "month":
            labels = [{"key": format_month(m), "label": format_month(m)} for m in data.months]
            series = [
                {
                    "key": metric,
                    "name": METRIC_NAMES[metric],
                    "color": None,
                    "values": [data.metric(metric, m) for m in data.months],
                }
            ]
            return labels, series
        if group == "month_category":
            ids = sorted(data.by_category(), key=lambda cid: data.by_category()[cid], reverse=True)
            labels = [{"key": format_month(m), "label": format_month(m)} for m in data.months]
            series = [
                {
                    "key": str(cid) if cid else "none",
                    "name": categories[cid].name if cid in categories else "Sem categoria",
                    "color": categories[cid].color if cid in categories else None,
                    "values": [_f(data.expenses.get(m, {}).get(cid, ZERO)) for m in data.months],
                }
                for cid in ids
            ]
            return labels, series
        if group == "month_type":
            labels = [{"key": format_month(m), "label": format_month(m)} for m in data.months]
            series = []
            for kind in ("essential", "non_essential"):
                values = []
                for m in data.months:
                    per = data.expenses.get(m, {})
                    total = sum(
                        (
                            v
                            for cid, v in per.items()
                            if (cid in essential_ids) == (kind == "essential")
                        ),
                        ZERO,
                    )
                    values.append(_f(total))
                series.append(
                    {
                        "key": kind,
                        "name": TYPE_LABELS[kind],
                        "color": TYPE_COLORS[kind],
                        "values": values,
                    }
                )
            return labels, series
        if group == "category":
            totals = data.by_category()
            ids = sorted(totals, key=lambda cid: totals[cid], reverse=True)
            labels = [
                {
                    "key": str(cid) if cid else "none",
                    "label": categories[cid].name if cid in categories else "Sem categoria",
                    "color": categories[cid].color if cid in categories else None,
                }
                for cid in ids
            ]
            series = [
                {
                    "key": "expenses",
                    "name": "Gastos",
                    "color": None,
                    "values": [_f(totals[c]) for c in ids],
                }
            ]
            return labels, series
        if group == "type":
            totals = data.by_category()
            essential = sum((v for cid, v in totals.items() if cid in essential_ids), ZERO)
            other = sum(totals.values(), ZERO) - essential
            labels = [
                {"key": k, "label": TYPE_LABELS[k], "color": TYPE_COLORS[k]}
                for k in ("essential", "non_essential")
            ]
            series = [
                {
                    "key": "expenses",
                    "name": "Gastos",
                    "color": None,
                    "values": [_f(essential), _f(other)],
                }
            ]
            return labels, series
        raise AppError(422, "invalid_group", "Agrupamento inválido.")

    labels, series = compute(start, end)

    def label_totals(series_list: list[dict[str, Any]], count: int) -> list[float | None]:
        if unit == "percent":
            return list(series_list[0]["values"])
        return [round(sum(s["values"][i] or 0 for s in series_list), 2) for i in range(count)]

    main_totals = label_totals(series, len(labels))
    compare_out = None
    if compare in ("previous", "last_year"):
        shift = len(months_between(start, end)) if compare == "previous" else 12
        other_labels, other_series = compute(add_months(start, -shift), add_months(end, -shift))
        other_totals = label_totals(other_series, len(other_labels))
        if group.startswith("month"):
            values = other_totals
        else:
            by_key = {lab["key"]: v for lab, v in zip(other_labels, other_totals, strict=True)}
            values = [by_key.get(lab["key"], 0.0) for lab in labels]
        compare_out = {"name": COMPARE_NAMES[compare], "values": values}
    elif compare == "average":
        avg_start, avg_end = add_months(start, -12), add_months(start, -1)
        other_labels, other_series = compute(avg_start, avg_end)
        other_totals = label_totals(other_series, len(other_labels))
        if group.startswith("month"):
            filled = [v for v in other_totals if v not in (None, 0.0)]
            mean = round(sum(filled) / len(filled), 2) if filled else None
            values = [mean] * len(labels)
        else:
            # Por categoria: média mensal dos 12 meses anteriores × meses do período.
            months = len(months_between(start, end))
            by_key = {lab["key"]: v for lab, v in zip(other_labels, other_totals, strict=True)}
            values = [round((by_key.get(lab["key"]) or 0) / 12 * months, 2) for lab in labels]
        compare_out = {"name": COMPARE_NAMES["average"], "values": values}

    def total(values: list[float | None]) -> float | None:
        present = [v for v in values if v is not None]
        if not present:
            return None
        return (
            round(sum(present) / len(present), 1) if unit == "percent" else round(sum(present), 2)
        )

    return {
        "labels": labels,
        "series": series,
        "compare": compare_out,
        "unit": unit,
        "total": total(main_totals),
        "compare_total": total(compare_out["values"]) if compare_out else None,
        "start": format_month(start),
        "end": format_month(end),
    }


# ---------------------------------------------------------------- análises salvas


def list_saved(db: Session, user: User) -> list[SavedAnalysis]:
    return list(
        db.scalars(
            select(SavedAnalysis)
            .where(SavedAnalysis.user_id == user.id)
            .order_by(SavedAnalysis.position, SavedAnalysis.created_at)
        )
    )


def _owned(db: Session, user: User, item_id: uuid.UUID) -> SavedAnalysis:
    item = db.get(SavedAnalysis, item_id)
    if item is None or item.user_id != user.id:
        raise AppError(404, "not_found", "Análise não encontrada.")
    return item


def create_saved(
    db: Session, user: User, name: str, config: dict[str, Any], pinned: bool
) -> SavedAnalysis:
    existing = list_saved(db, user)
    if len(existing) >= MAX_SAVED:
        raise AppError(422, "too_many", f"Você pode salvar até {MAX_SAVED} análises.")
    item = SavedAnalysis(
        user_id=user.id,
        name=name,
        config=json.dumps(config, ensure_ascii=False),
        pinned=pinned,
        position=len(existing),
    )
    db.add(item)
    db.commit()
    return item


def update_saved(
    db: Session, user: User, item_id: uuid.UUID, changes: dict[str, Any]
) -> SavedAnalysis:
    item = _owned(db, user, item_id)
    if "config" in changes:
        changes["config"] = json.dumps(changes["config"], ensure_ascii=False)
    for key, value in changes.items():
        setattr(item, key, value)
    db.commit()
    return item


def delete_saved(db: Session, user: User, item_id: uuid.UUID) -> None:
    db.delete(_owned(db, user, item_id))
    db.commit()
