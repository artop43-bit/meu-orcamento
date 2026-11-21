"""Consultas especializadas do orçamento diário, salário, registros do dia, fixos e revisão."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Expense, Income, PlannedExpense, RecurringItem, User
from app.services import daily
from app.services.bot.contracts import QueryPlan
from app.services.bot.lexicon import core
from app.services.bot.months import format_month, month_label, month_of, short_date
from app.services.bot.nlu.filters import UserEntityIndex
from app.services.bot.text_utils import brl, cap, normalize, pct, plural, signed_brl


def can_spend_summary(db: Session, user: User, today: date) -> dict[str, Any]:
    current = month_of(today, user.month_start_day)
    forecast = daily.forecast(db, user, current, today)
    can = forecast.get("can_spend")
    links = [{"label": "Abrir o Orçamento", "to": "/orcamento"}]
    if not can:
        return {
            "intent": "can_spend",
            "answer": f"O saldo previsto para o fim do mês é {signed_brl(forecast['end_balance'])}.",
            "links": links,
        }
    if can["rest_of_month"] <= 0:
        text = "Hoje não há saldo livre: as despesas previstas consomem toda a receita do mês."
        if forecast.get("first_negative"):
            text += f" O saldo fica negativo a partir de {short_date(forecast['first_negative'])}."
    else:
        text = (
            f"Hoje você pode gastar até {brl(can['today'])}. "
            f"São {brl(can['rest_of_month'])} livres até o fim do mês, em "
            f"{plural(can['days_left'], 'dia', 'dias')}, já descontando tudo o que está previsto."
        )
    return {"intent": "can_spend", "answer": text, "links": links}


def salary_summary(db: Session, user: User, today: date) -> dict[str, Any]:
    current = month_of(today, user.month_start_day)
    incomes = list(
        db.scalars(
            select(Income)
            .where(Income.user_id == user.id, Income.month <= current)
            .order_by(Income.month.desc(), Income.amount.desc())
        )
    )
    salary_rows = [
        i
        for i in incomes
        if any(tok in normalize(i.description) for tok in ("salario", "holerite", "pro labore"))
    ]
    if not salary_rows:
        salary_rows = [i for i in incomes if i.income_type == "fixed"]
    if not salary_rows:
        return {
            "intent": "salary",
            "answer": "Não encontrei salário cadastrado nas suas receitas.",
            "items": [],
            "links": [{"label": "Abrir o Orçamento", "to": "/orcamento"}],
            "suggestions": ["Quanto recebi este mês?"],
        }
    latest = salary_rows[0]
    day_txt = f" (cai no dia {latest.day})" if latest.day else ""
    return {
        "intent": "salary",
        "answer": f"Seu último salário registrado foi {brl(latest.amount)} em {month_label(latest.month)}{day_txt}.",
        "items": [
            {
                "label": i.description,
                "detail": month_label(i.month) + (f" · dia {i.day}" if i.day else ""),
                "value": brl(i.amount),
                "link": f"/orcamento/{format_month(i.month)}",
            }
            for i in salary_rows[:5]
        ],
        "links": [{"label": "Abrir o Orçamento", "to": f"/orcamento/{format_month(latest.month)}"}],
        "suggestions": ["Quanto recebi este mês?", "Quanto sobrou este mês?"],
    }


def logged_summary(db: Session, user: User, plan: QueryPlan, today: date) -> dict[str, Any]:
    period = plan.filters.period
    d_start = period.day_start if period and period.day_start else today
    d_end = period.day_end if period and period.day_end else today
    label = period.label if period else "hoje"
    zone = ZoneInfo(get_settings().timezone)
    since = datetime.combine(d_start, datetime.min.time(), zone)
    until = datetime.combine(d_end + timedelta(days=1), datetime.min.time(), zone)

    exps = list(
        db.scalars(
            select(Expense)
            .where(
                Expense.user_id == user.id, Expense.created_at >= since, Expense.created_at < until
            )
            .order_by(Expense.created_at.desc())
        )
    )
    incs = list(
        db.scalars(
            select(Income)
            .where(Income.user_id == user.id, Income.created_at >= since, Income.created_at < until)
            .order_by(Income.created_at.desc())
        )
    )
    if len(exps) + len(incs) == 0:
        return {
            "intent": "logged",
            "answer": f"Você não registrou nenhum lançamento {label}.",
            "items": [],
            "links": [{"label": "Abrir o Orçamento", "to": "/orcamento"}],
            "suggestions": ["Quanto gastei esta semana?", "Qual foi meu último lançamento?"],
        }
    parts: list[str] = []
    if exps:
        parts.append(
            f"{plural(len(exps), 'despesa', 'despesas')} ({brl(sum((e.amount for e in exps), Decimal(0)))})"
        )
    if incs:
        parts.append(
            f"{plural(len(incs), 'receita', 'receitas')} ({brl(sum((i.amount for i in incs), Decimal(0)))})"
        )
    items = [
        {
            "label": e.description,
            "detail": short_date(e.purchase_date or e.due_date or e.month),
            "value": brl(e.amount),
            "link": f"/orcamento/{format_month(e.month)}",
        }
        for e in exps[:6]
    ] + [
        {
            "label": i.description,
            "detail": f"Receita · {month_label(i.month)}",
            "value": brl(i.amount),
            "link": f"/orcamento/{format_month(i.month)}",
        }
        for i in incs[:4]
    ]
    return {
        "intent": "logged",
        "answer": f"{cap(label)}, você registrou {' e '.join(parts)}.",
        "items": items,
        "links": [{"label": "Abrir o Orçamento", "to": "/orcamento"}],
        "suggestions": [],
    }


def recurring_summary(
    db: Session, user: User, plan: QueryPlan, index: UserEntityIndex, today: date
) -> dict[str, Any]:
    only_subs = "assinatura" in plan.corrected_question
    current = month_of(today, user.month_start_day)
    rows = [
        r
        for r in db.scalars(
            select(RecurringItem).where(
                RecurringItem.user_id == user.id, RecurringItem.kind == "expense"
            )
        )
        if r.end_month is None or r.end_month >= current
    ]
    cat_map = {c.id: c.name for c in index.categories}
    if only_subs:
        rows = [
            r
            for r in rows
            if normalize(cat_map.get(r.category_id, "")) == "assinaturas"
            or core.keyword_category(r.description) == "Assinaturas"
        ]
    label = "assinaturas" if only_subs else "despesas fixas"
    if not rows:
        return {
            "intent": "recurring",
            "answer": f"Não encontrei {label} cadastradas nas recorrências.",
            "items": [],
            "links": [{"label": "Abrir recorrências", "to": "/ajustes/recorrencias"}],
            "suggestions": [],
        }
    monthly = sum((r.amount / max(r.interval_months or 1, 1) for r in rows), Decimal(0))
    rows.sort(key=lambda r: -r.amount)
    return {
        "intent": "recurring",
        "answer": f"Você tem {plural(len(rows), 'assinatura', 'assinaturas') if only_subs else plural(len(rows), 'despesa fixa', 'despesas fixas')}, somando {brl(monthly)} por mês.",
        "items": [
            {
                "label": r.description,
                "detail": " · ".join(
                    x
                    for x in (cat_map.get(r.category_id), f"dia {r.due_day}" if r.due_day else None)
                    if x
                ),
                "value": brl(r.amount),
                "link": "/ajustes/recorrencias",
            }
            for r in rows[:8]
        ],
        "links": [{"label": "Abrir recorrências", "to": "/ajustes/recorrencias"}],
        "suggestions": [],
    }


def projects_summary(
    db: Session, user: User, plan: QueryPlan, index: UserEntityIndex
) -> dict[str, Any]:
    projs = index.projects
    if plan.filters.project_ids:
        projs = [p for p in projs if p.id in plan.filters.project_ids]
    if not projs:
        return {
            "intent": "projects",
            "answer": "Você ainda não tem projetos ou etiquetas cadastrados.",
            "items": [],
            "links": [{"label": "Abrir projetos", "to": "/ajustes/projetos"}],
            "suggestions": [],
        }
    exps = list(
        db.scalars(
            select(Expense).where(Expense.user_id == user.id, Expense.project_id.is_not(None))
        )
    )
    items = []
    total_all = Decimal(0)
    for p in projs:
        spent = sum((e.amount for e in exps if e.project_id == p.id), Decimal(0))
        total_all += spent
        detail = (
            f"teto {brl(p.budget)} ({pct(spent, p.budget)})" if p.budget else "sem teto definido"
        )
        items.append({"label": p.name, "detail": detail, "value": brl(spent), "link": "/orcamento"})
    return {
        "intent": "projects",
        "answer": f"Você tem {plural(len(projs), 'projeto', 'projetos')}, somando {brl(total_all)} em despesas vinculadas.",
        "items": items[:6],
        "links": [{"label": "Abrir projetos", "to": "/ajustes/projetos"}],
        "suggestions": [],
    }


def planned_summary(db: Session, user: User, today: date) -> dict[str, Any]:
    rows = list(
        db.scalars(
            select(PlannedExpense)
            .where(
                PlannedExpense.user_id == user.id,
                PlannedExpense.expense_id.is_(None),
                PlannedExpense.date >= today,
            )
            .order_by(PlannedExpense.date)
        )
    )
    if not rows:
        return {
            "intent": "planned",
            "answer": "Não há gastos futuros planejados em aberto.",
            "items": [],
            "links": [{"label": "Abrir calendário", "to": "/calendario"}],
            "suggestions": [],
        }
    total = sum((p.amount for p in rows), Decimal(0))
    return {
        "intent": "planned",
        "answer": f"Há {plural(len(rows), 'gasto planejado', 'gastos planejados')} para os próximos dias, somando {brl(total)}.",
        "items": [
            {
                "label": p.description,
                "detail": short_date(p.date),
                "value": brl(p.amount),
                "link": "/calendario",
            }
            for p in rows[:6]
        ],
        "links": [{"label": "Abrir calendário", "to": "/calendario"}],
        "suggestions": [],
    }


def review_pending_summary(db: Session, user: User) -> dict[str, Any]:
    rows = list(
        db.scalars(
            select(Expense).where(Expense.user_id == user.id, Expense.needs_review.is_(True))
        )
    )
    if not rows:
        return {
            "intent": "review_pending",
            "answer": "Nenhum lançamento pendente de revisão. Tudo conferido!",
            "items": [],
            "links": [{"label": "Abrir revisar", "to": "/revisar"}],
            "suggestions": [],
        }
    total = sum((e.amount for e in rows), Decimal(0))
    return {
        "intent": "review_pending",
        "answer": f"Há {plural(len(rows), 'lançamento pendente', 'lançamentos pendentes')} de revisão, somando {brl(total)}.",
        "items": [
            {
                "label": e.description,
                "detail": f"em {month_label(e.month)}",
                "value": brl(e.amount),
                "link": "/revisar",
            }
            for e in rows[:6]
        ],
        "links": [{"label": "Revisar lançamentos", "to": "/revisar"}],
        "suggestions": [],
    }
