"""Motor universal de consultas analíticas combinando filtros, agrupamentos e métricas."""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Expense, Income, User
from app.services.bot.contracts import PeriodSpec, QueryFilters, QueryPlan
from app.services.bot.lexicon import core
from app.services.bot.months import (
    add_months,
    cycle_date,
    cycle_range,
    format_month,
    month_label,
    month_of,
    short_date,
)
from app.services.bot.nlu.filters import UserEntityIndex
from app.services.bot.nlu.periods import default_all_time, default_month, default_year
from app.services.bot.text_utils import brl, cap, dice_trigram, normalize, pct, plural, signed_brl


@dataclass
class _Record:
    kind: str  # expense | income
    when: date
    month: date
    amount: Decimal
    description: str
    notes: str | None
    category_id: uuid.UUID | None
    card_id: uuid.UUID | None
    account_id: uuid.UUID | None
    project_id: uuid.UUID | None
    payment_method: str | None
    paid: bool


def _expense_when(e: Expense) -> date:
    return e.purchase_date or e.due_date or e.month


def _income_when(i: Income, start_day: int) -> date:
    return cycle_date(i.month, i.day, start_day) if i.day else i.month


def _filter_summary(f: QueryFilters) -> str:
    parts: list[str] = []
    if f.category_names:
        parts.append("com " + ", ".join(f.category_names))
    if f.card_names:
        parts.append("no cartão " + ", ".join(f.card_names))
    if f.account_names:
        parts.append("na conta " + ", ".join(f.account_names))
    if f.project_names:
        parts.append("no projeto " + ", ".join(f.project_names))
    if f.payment_methods:
        parts.append("no " + "/".join(core.PAYMENT_LABELS.get(m, m) for m in f.payment_methods))
    if f.text_terms:
        parts.append("com " + " ".join(f.text_terms))
    if amt := f.amount.describe():
        parts.append(amt)
    if f.paid is True:
        parts.append("já pagos")
    elif f.paid is False:
        parts.append("em aberto")
    if f.overdue is True:
        parts.append("atrasados")
    if f.is_installment is True:
        parts.append("parcelados")
    if f.is_recurring is True:
        parts.append("fixos")
    if f.is_essential is True:
        parts.append("essenciais")
    elif f.is_essential is False:
        parts.append("não essenciais")
    if f.deductible:
        parts.append("dedutíveis no IR")
    if f.mei:
        parts.append("do MEI")
    return " ".join(parts)


def _subject_name(f: QueryFilters) -> str:
    if f.category_names:
        return ", ".join(f.category_names)
    if f.card_names:
        return "cartão " + ", ".join(f.card_names)
    if f.project_names:
        return "projeto " + ", ".join(f.project_names)
    if f.text_terms:
        return " ".join(f.text_terms)
    return _filter_summary(f)


def _matches_text(text: str, notes: str | None, terms: list[str]) -> bool:
    if not terms:
        return True
    hay = normalize(f"{text} {notes or ''}")
    hay_tokens = hay.split()
    for term in terms:
        if " " in term:
            if f" {term} " in f" {hay} ":
                continue
        elif (
            term in hay_tokens
            or (len(term) >= 4 and any(tok.startswith(term) for tok in hay_tokens))
            or (len(term) >= 6 and any(term in tok for tok in hay_tokens))
        ):
            continue
        if len(term) >= 4 and any(dice_trigram(term, tok) >= 0.68 for tok in hay_tokens):
            continue
        return False
    return True


def fetch_records(
    db: Session,
    user: User,
    period: PeriodSpec,
    filters: QueryFilters,
    domain: str,
    index: UserEntityIndex,
    today: date,
) -> list[_Record]:
    start, end = period.start, period.end
    if period.day_start and period.day_end:
        start = add_months(min(start, period.day_start.replace(day=1)), -1)
        end = add_months(max(end, period.day_end.replace(day=1)), 2)

    cat_map = {c.id: c for c in index.categories}
    records: list[_Record] = []

    if domain != "income":
        q = select(Expense).where(Expense.user_id == user.id)
        if not period.all_time:
            q = q.where(Expense.month.between(start, end))
        if filters.category_ids:
            q = q.where(Expense.category_id.in_(filters.category_ids))
        if filters.card_ids:
            q = q.where(
                Expense.card_id.in_(filters.card_ids) | Expense.debit_card_id.in_(filters.card_ids)
            )
        if filters.account_ids:
            q = q.where(Expense.account_id.in_(filters.account_ids))
        if filters.project_ids:
            q = q.where(Expense.project_id.in_(filters.project_ids))
        if filters.payment_methods:
            q = q.where(Expense.payment_method.in_(filters.payment_methods))
        if filters.paid is not None:
            q = q.where(Expense.paid.is_(filters.paid))
        if filters.needs_review is not None:
            q = q.where(Expense.needs_review.is_(filters.needs_review))
        if filters.is_installment is True:
            q = q.where(Expense.installment_group_id.is_not(None))
        if filters.is_recurring is True:
            q = q.where(Expense.recurring_id.is_not(None))

        for e in db.scalars(q):
            when = _expense_when(e)
            if (
                period.day_start
                and period.day_end
                and not (period.day_start <= when <= period.day_end)
            ):
                continue
            if filters.overdue is True and not (
                not e.paid and e.due_date is not None and e.due_date < today
            ):
                continue
            if not filters.amount.matches(e.amount):
                continue
            cat = cat_map.get(e.category_id) if e.category_id else None
            if filters.is_essential is not None:
                if cat is None or cat.is_essential != filters.is_essential:
                    continue
            if filters.deductible is not None:
                if cat is None or not cat.deductible:
                    continue
                if filters.deductible != "any" and cat.deductible != filters.deductible:
                    continue
            if not _matches_text(e.description, e.notes, filters.text_terms):
                continue
            records.append(
                _Record(
                    kind="expense",
                    when=when,
                    month=e.month,
                    amount=e.amount,
                    description=e.description,
                    notes=e.notes,
                    category_id=e.category_id,
                    card_id=e.card_id or e.debit_card_id,
                    account_id=e.account_id,
                    project_id=e.project_id,
                    payment_method=e.payment_method,
                    paid=e.paid,
                )
            )

    if domain == "income":
        q = select(Income).where(Income.user_id == user.id)
        if not period.all_time:
            q = q.where(Income.month.between(start, end))
        if filters.account_ids:
            q = q.where(Income.account_id.in_(filters.account_ids))
        if filters.mei is True:
            q = q.where(Income.mei.is_(True))
        for i in db.scalars(q):
            when = _income_when(i, user.month_start_day)
            if (
                period.day_start
                and period.day_end
                and not (period.day_start <= when <= period.day_end)
            ):
                continue
            if not filters.amount.matches(i.amount):
                continue
            if not _matches_text(i.description, i.notes, filters.text_terms):
                continue
            records.append(
                _Record(
                    kind="income",
                    when=when,
                    month=i.month,
                    amount=i.amount,
                    description=i.description,
                    notes=i.notes,
                    category_id=None,
                    card_id=None,
                    account_id=i.account_id,
                    project_id=None,
                    payment_method=None,
                    paid=True,
                )
            )

    return records


def _record_item(r: _Record, index: UserEntityIndex) -> dict[str, Any]:
    cat_map = {c.id: c.name for c in index.categories}
    card_map = {c.id: c.name for c in index.cards}
    acc_map = {a.id: a.name for a in index.accounts}
    details = [short_date(r.when)]
    if r.category_id and r.category_id in cat_map:
        details.append(cat_map[r.category_id])
    if r.payment_method:
        details.append(core.PAYMENT_LABELS.get(r.payment_method, r.payment_method))
    if r.card_id and r.card_id in card_map:
        details.append(card_map[r.card_id])
    elif r.account_id and r.account_id in acc_map:
        details.append(acc_map[r.account_id])
    return {
        "label": r.description,
        "detail": " · ".join(details),
        "value": brl(r.amount),
        "link": f"/orcamento/{format_month(r.month)}",
    }


def _group_key(r: _Record, grouping: str) -> Any:
    if grouping == "year":
        return r.month.year
    if grouping == "quarter":
        q = (r.month.month - 1) // 3 + 1
        return (r.month.year, q)
    if grouping == "semester":
        s = 1 if r.month.month <= 6 else 2
        return (r.month.year, s)
    if grouping == "month":
        return r.month
    if grouping == "week":
        return r.when - timedelta(days=r.when.weekday())
    if grouping == "day":
        return r.when
    if grouping == "weekday":
        return r.when.weekday()
    if grouping == "category":
        return r.category_id or "__none__"
    if grouping == "card":
        return r.card_id or "__none__"
    if grouping == "account":
        return r.account_id or "__none__"
    if grouping == "project":
        return r.project_id or "__none__"
    if grouping == "payment_method":
        return r.payment_method or "__none__"
    if grouping == "status":
        return "Pago" if r.paid else "Em aberto"
    return normalize(r.description)


def _group_label(
    key: Any, grouping: str, index: UserEntityIndex, sample_names: dict[Any, str]
) -> str:
    if grouping == "year":
        return str(key)
    if grouping == "quarter":
        return f"{key[1]}º trimestre de {key[0]}"
    if grouping == "semester":
        return f"{key[1]}º semestre de {key[0]}"
    if grouping == "month":
        return month_label(key)
    if grouping == "week":
        end = key + timedelta(days=6)
        return f"{key.day:02d}/{key.month:02d} a {end.day:02d}/{end.month:02d}/{end.year}"
    if grouping == "day":
        return f"{short_date(key)} ({core.WEEKDAY_LABELS[key.weekday()]})"
    if grouping == "weekday":
        return core.WEEKDAY_LABELS[key]
    if grouping == "category":
        if key == "__none__":
            return "Sem categoria"
        return next((c.name for c in index.categories if c.id == key), "Sem categoria")
    if grouping == "card":
        if key == "__none__":
            return "Sem cartão (à vista/outro)"
        return next((c.name for c in index.cards if c.id == key), "Cartão")
    if grouping == "account":
        if key == "__none__":
            return "Sem conta vinculada"
        return next((a.name for a in index.accounts if a.id == key), "Conta")
    if grouping == "project":
        if key == "__none__":
            return "Sem projeto"
        return next((p.name for p in index.projects if p.id == key), "Projeto")
    if grouping == "payment_method":
        if key == "__none__":
            return "Não informado"
        return core.PAYMENT_LABELS.get(key, str(key))
    if grouping == "status":
        return str(key)
    return sample_names.get(key, str(key))


_UNIT_LABELS: dict[str, tuple[str, str, str]] = {
    "year": ("ano", "o ano", "anos"),
    "quarter": ("trimestre", "o trimestre", "trimestres"),
    "semester": ("semestre", "o semestre", "semestres"),
    "month": ("mês", "o mês", "meses"),
    "week": ("semana", "a semana", "semanas"),
    "day": ("dia", "o dia", "dias"),
    "weekday": ("dia da semana", "o dia da semana", "dias da semana"),
    "category": ("categoria", "a categoria", "categorias"),
    "place": ("lugar", "o lugar", "lugares"),
    "payment_method": ("forma de pagamento", "a forma de pagamento", "formas de pagamento"),
    "card": ("cartão", "o cartão", "cartões"),
    "account": ("conta", "a conta", "contas"),
    "project": ("projeto", "o projeto", "projetos"),
    "status": ("status", "o status", "status"),
}


def _resolve_analytic_period(
    db: Session,
    user: User,
    plan: QueryPlan,
    index: UserEntityIndex,
    today: date,
    current: date,
) -> PeriodSpec:
    f = plan.filters
    if f.period is not None:
        return f.period
    if plan.intent == "rank_group" and plan.grouping == "year":
        return default_all_time(current)
    if plan.intent in {"rank_group", "series"} and plan.grouping == "month":
        return default_year(current)
    if plan.intent == "series" and plan.grouping == "year":
        return default_all_time(current)
    if plan.intent == "avg" and (plan.grouping or "month") == "month":
        # Média mensal usa os últimos meses fechados (ou todo o histórico se só existir o mês atual)
        prev_end = add_months(current, -1)
        prev_start = add_months(current, -6)
        closed_period = PeriodSpec(
            prev_start, prev_end, "nos últimos meses fechados", explicit=False
        )
        if fetch_records(db, user, closed_period, f, plan.domain, index, today):
            return closed_period
        return default_all_time(current)
    if (
        plan.intent in {"extreme_item", "latest_item"}
        or f.project_ids
        or f.amount.min_amount is not None
        or f.amount.max_amount is not None
        or f.amount.target_amount is not None
    ):
        return default_all_time(current)
    return default_month(current)


def _exec_balance(
    db: Session,
    user: User,
    f: QueryFilters,
    period: PeriodSpec,
    about_txt: str,
    index: UserEntityIndex,
    today: date,
) -> dict[str, Any]:
    exp = fetch_records(db, user, period, f, "expense", index, today)
    inc = fetch_records(db, user, period, f, "income", index, today)
    spent = sum((r.amount for r in exp), Decimal(0))
    earned = sum((r.amount for r in inc), Decimal(0))
    diff = earned - spent
    word = "Sobraram" if diff >= 0 else "Faltaram"
    return {
        "intent": "balance",
        "answer": f"{cap(period.label)}{about_txt}: receitas de {brl(earned)}, despesas de {brl(spent)}. {word} {brl(diff)}.",
        "items": [
            {
                "label": "Receitas",
                "detail": plural(len(inc), "lançamento", "lançamentos"),
                "value": brl(earned),
                "link": None,
            },
            {
                "label": "Despesas",
                "detail": plural(len(exp), "lançamento", "lançamentos"),
                "value": brl(spent),
                "link": None,
            },
            {"label": "Saldo", "detail": None, "value": signed_brl(diff), "link": None},
        ],
        "links": [{"label": "Ver Insights", "to": "/analises"}],
        "suggestions": ["O que mais gastei este mês?", "Qual mês gastei mais este ano?"],
    }


def _exec_compare(
    db: Session,
    user: User,
    plan: QueryPlan,
    f: QueryFilters,
    about_txt: str,
    index: UserEntityIndex,
    today: date,
    current: date,
) -> dict[str, Any]:
    p1 = f.period or default_month(current)
    p2 = f.period2
    if p2 is None:
        prev = add_months(p1.start, -1)
        p2 = PeriodSpec(prev, prev, f"em {month_label(prev)}")
    if p2.start > p1.start:
        p1, p2 = p2, p1
    rows_a = fetch_records(db, user, p1, f, plan.domain, index, today)
    rows_b = fetch_records(db, user, p2, f, plan.domain, index, today)
    tot_a = sum((r.amount for r in rows_a), Decimal(0))
    tot_b = sum((r.amount for r in rows_b), Decimal(0))
    if not rows_a and not rows_b:
        return {
            "intent": "empty",
            "answer": f"Não encontrei lançamentos{about_txt} nem {p1.label} nem {p2.label}.",
            "items": [],
            "links": [],
            "suggestions": [],
        }
    diff = tot_a - tot_b
    if diff == 0:
        verdict = "exatamente o mesmo valor"
    else:
        p_str = f" ({abs(diff) / tot_b * 100:.0f}%)" if tot_b else ""
        verdict = f"{brl(diff)}{p_str} {'a mais' if diff > 0 else 'a menos'}"
    return {
        "intent": "compare",
        "answer": f"{cap(p1.label)} foram {brl(tot_a)}{about_txt}; {p2.label}, {brl(tot_b)}. Diferença de {verdict}.",
        "items": [
            {
                "label": cap(p1.label),
                "detail": plural(len(rows_a), "lançamento", "lançamentos"),
                "value": brl(tot_a),
                "link": None,
            },
            {
                "label": cap(p2.label),
                "detail": plural(len(rows_b), "lançamento", "lançamentos"),
                "value": brl(tot_b),
                "link": None,
            },
            {
                "label": "Variação",
                "detail": None,
                "value": ("+" if diff > 0 else "−" if diff < 0 else "") + brl(diff),
                "link": None,
            },
        ],
        "links": [{"label": "Comparar meses nos Insights", "to": "/analises?secao=comparar"}],
        "suggestions": ["Qual mês gastei mais este ano?"],
    }


def _exec_percent(
    db: Session,
    user: User,
    plan: QueryPlan,
    rows: list[_Record],
    period: PeriodSpec,
    about: str,
    index: UserEntityIndex,
    today: date,
) -> dict[str, Any]:
    part = sum((r.amount for r in rows), Decimal(0))
    of_income = plan.grouping == "of_income"
    all_inc = fetch_records(db, user, period, QueryFilters(), "income", index, today)
    all_exp = fetch_records(db, user, period, QueryFilters(), "expense", index, today)
    earned = sum((r.amount for r in all_inc), Decimal(0))
    spent_total = sum((r.amount for r in all_exp), Decimal(0))
    whole = earned if of_income else spent_total
    if whole <= 0:
        missing = "receitas" if of_income else "despesas"
        return {
            "intent": "percent",
            "answer": f"Não há {missing} lançadas {period.label} para calcular o percentual.",
            "items": [],
            "links": [{"label": "Abrir o Orçamento", "to": "/orcamento"}],
            "suggestions": [],
        }
    share = pct(part, whole)
    subj = _subject_name(plan.filters)
    if of_income and not about:
        diff = earned - part
        diff_word = "Sobraram" if diff >= 0 else "Faltaram"
        ans = (
            f"{cap(period.label)}, você gastou {brl(part)} de {brl(earned)} recebidos: "
            f"{share} das receitas. {diff_word} {brl(diff)}."
        )
        items = [
            {"label": "Receitas", "detail": None, "value": brl(earned), "link": None},
            {"label": "Despesas", "detail": None, "value": brl(part), "link": None},
            {"label": "Percentual das receitas", "detail": None, "value": share, "link": None},
        ]
    elif of_income:
        ans = f"{cap(period.label)}, {subj} levou {share} das suas receitas ({brl(part)} de {brl(earned)})."
        items = [
            {"label": subj, "detail": None, "value": brl(part), "link": None},
            {"label": "Receitas", "detail": None, "value": brl(earned), "link": None},
            {"label": "Percentual das receitas", "detail": None, "value": share, "link": None},
        ]
    else:
        ans = f"{cap(period.label)}, {subj or 'esse recorte'} foi {share} dos seus gastos ({brl(part)} de {brl(spent_total)})."
        items = [
            {"label": subj or "Recorte", "detail": None, "value": brl(part), "link": None},
            {"label": "Despesas", "detail": None, "value": brl(spent_total), "link": None},
            {"label": "Percentual dos gastos", "detail": None, "value": share, "link": None},
        ]
    return {
        "intent": "percent",
        "answer": ans,
        "items": items,
        "links": [{"label": "Ver categorias nos Insights", "to": "/analises?secao=categorias"}],
        "suggestions": [],
    }


def _exec_count(
    plan: QueryPlan,
    rows: list[_Record],
    period: PeriodSpec,
    about_txt: str,
    index: UserEntityIndex,
) -> dict[str, Any]:
    f = plan.filters
    total = sum((r.amount for r in rows), Decimal(0))
    unit_s, unit_p = (
        ("receita", "receitas") if plan.domain == "income" else ("lançamento", "lançamentos")
    )
    latest = sorted(rows, key=lambda r: r.when, reverse=True)[: plan.limit]
    if f.text_terms and not (
        f.category_names or f.card_names or f.account_names or f.project_names
    ):
        term_txt = f" com “{' '.join(f.text_terms)}”"
        ans = f"{cap(period.label)}, foram {plural(len(rows), unit_s, unit_p)}{term_txt}, somando {brl(total)} (média de {brl(total / len(rows))} cada)."
    else:
        ans = f"{cap(period.label)}{about_txt} foram {plural(len(rows), unit_s, unit_p)}, somando {brl(total)} (média de {brl(total / len(rows))} cada)."
    return {
        "intent": "count",
        "answer": ans,
        "items": [_record_item(r, index) for r in latest],
        "links": [],
        "suggestions": [],
    }


def _exec_extreme_item(
    plan: QueryPlan,
    rows: list[_Record],
    period: PeriodSpec,
    about_txt: str,
    index: UserEntityIndex,
) -> dict[str, Any]:
    reverse = plan.order == "most"
    ranked = sorted(rows, key=lambda r: (r.amount, r.when), reverse=reverse)[: plan.limit]
    top = ranked[0]
    total = sum((r.amount for r in rows), Decimal(0))
    if reverse:
        kind_word = "receita" if plan.domain == "income" else "despesa"
        ans = (
            f"{cap(period.label)}{about_txt}, a maior {kind_word} foi {top.description}: "
            f"{brl(top.amount)} em {short_date(top.when)} (no orçamento de {month_label(top.month)}). "
            f"No recorte todo foram {brl(total)} em {plural(len(rows), 'lançamento', 'lançamentos')}."
        )
    else:
        ans = (
            f"{cap(period.label)}{about_txt}, o menor foi {top.description}, "
            f"{brl(top.amount)} em {short_date(top.when)} (no orçamento de {month_label(top.month)})."
        )
    return {
        "intent": "biggest" if reverse else "smallest",
        "answer": ans,
        "items": [_record_item(r, index) for r in ranked],
        "links": [
            {
                "label": f"Abrir {month_label(top.month)}",
                "to": f"/orcamento/{format_month(top.month)}",
            }
        ],
        "suggestions": ["Qual ano mais gastei?", "O que mais gastei este mês?"],
    }


def _exec_latest_item(
    plan: QueryPlan, rows: list[_Record], about_txt: str, index: UserEntityIndex
) -> dict[str, Any]:
    ranked = sorted(rows, key=lambda r: r.when, reverse=True)[: plan.limit]
    last = ranked[0]
    kind_word = "receita" if plan.domain == "income" else "despesa"
    return {
        "intent": "last_income" if plan.domain == "income" else "last",
        "answer": f"A última {kind_word}{about_txt} foi {last.description}, {brl(last.amount)} em {short_date(last.when)} (orçamento de {month_label(last.month)}).",
        "items": [_record_item(r, index) for r in ranked],
        "links": [
            {
                "label": f"Abrir {month_label(last.month)}",
                "to": f"/orcamento/{format_month(last.month)}",
            }
        ],
        "suggestions": [],
    }


def _exec_list_records(
    plan: QueryPlan,
    rows: list[_Record],
    period: PeriodSpec,
    about_txt: str,
    index: UserEntityIndex,
) -> dict[str, Any]:
    ranked = sorted(rows, key=lambda r: (r.when, r.amount), reverse=True)[: max(plan.limit, 8)]
    total = sum((r.amount for r in rows), Decimal(0))
    return {
        "intent": "list_records",
        "answer": f"{cap(period.label)}{about_txt}, encontrei {plural(len(rows), 'lançamento', 'lançamentos')}, somando {brl(total)}.",
        "items": [_record_item(r, index) for r in ranked],
        "links": [
            {"label": "Abrir o Orçamento", "to": f"/orcamento/{format_month(ranked[0].month)}"}
        ],
        "suggestions": [],
    }


def _group_rows(
    rows: list[_Record], grouping: str
) -> tuple[dict[Any, Decimal], dict[Any, int], dict[Any, date], dict[Any, str]]:
    totals: dict[Any, Decimal] = defaultdict(Decimal)
    counts: dict[Any, int] = defaultdict(int)
    sample_months: dict[Any, date] = {}
    sample_names: dict[Any, str] = {}
    for r in rows:
        k = _group_key(r, grouping)
        totals[k] += r.amount
        counts[k] += 1
        sample_months.setdefault(k, r.month)
        sample_names.setdefault(k, r.description)
    return totals, counts, sample_months, sample_names


def _exec_rank_group(
    plan: QueryPlan,
    rows: list[_Record],
    period: PeriodSpec,
    about_txt: str,
    index: UserEntityIndex,
) -> dict[str, Any]:
    grouping = plan.grouping or "category"
    totals, counts, sample_months, sample_names = _group_rows(rows, grouping)
    reverse = plan.order == "most"
    ranked_keys = sorted(totals, key=lambda k: totals[k], reverse=reverse)
    first = ranked_keys[0]
    first_label = _group_label(first, grouping, index, sample_names)
    total_all = sum(totals.values(), Decimal(0))
    avg_group = total_all / len(totals)
    unit_s, article, unit_p = _UNIT_LABELS.get(grouping, ("grupo", "o grupo", "grupos"))
    verb = "recebeu" if plan.domain == "income" else "gastou"
    more_less = "mais" if reverse else "menos"
    items = [
        {
            "label": cap(_group_label(k, grouping, index, sample_names)),
            "detail": f"{plural(counts[k], 'lançamento', 'lançamentos')} · {pct(totals[k], total_all)}",
            "value": brl(totals[k]),
            "link": f"/orcamento/{format_month(sample_months[k])}"
            if grouping in {"month", "week", "day"}
            else None,
        }
        for k in ranked_keys[: plan.limit]
    ]
    lead = (
        f"onde você {more_less} {verb}{about_txt} foi"
        if grouping == "place"
        else f"{article} em que você {more_less} {verb}{about_txt} foi"
    )
    links: list[dict[str, str]] = []
    if grouping in {"month", "week", "day"}:
        links.append(
            {
                "label": f"Abrir {cap(month_label(sample_months[first]))}",
                "to": f"/orcamento/{format_month(sample_months[first])}",
            }
        )
    links.append({"label": "Ver Insights", "to": "/analises"})
    intent_name = (
        "top_categories"
        if grouping == "category" and reverse
        else f"{grouping}_{'max' if reverse else 'min'}"
    )
    return {
        "intent": intent_name,
        "answer": (
            f"{cap(period.label)}, {lead} "
            f"{first_label}: {brl(totals[first])} ({pct(totals[first], total_all)} de {brl(total_all)}). "
            f"Foram {len(totals)} {unit_p}, com média de {brl(avg_group)} por {unit_s}."
        ),
        "items": items,
        "links": links,
        "suggestions": [],
    }


def _exec_series(
    plan: QueryPlan,
    rows: list[_Record],
    period: PeriodSpec,
    about_txt: str,
    index: UserEntityIndex,
) -> dict[str, Any]:
    grouping = plan.grouping or "month"
    totals, counts, sample_months, sample_names = _group_rows(rows, grouping)
    keys = sorted(totals)
    total_all = sum(totals.values(), Decimal(0))
    unit_s, _, unit_p = _UNIT_LABELS.get(grouping, ("período", "o período", "períodos"))
    shown = keys[-12:]
    return {
        "intent": f"{grouping}_list",
        "answer": (
            f"{cap(period.label)}{about_txt} foram {brl(total_all)} em {len(keys)} "
            f"{unit_p if len(keys) > 1 else unit_s} (média de {brl(total_all / len(keys))} por {unit_s})."
        ),
        "items": [
            {
                "label": cap(_group_label(k, grouping, index, sample_names)),
                "detail": plural(counts[k], "lançamento", "lançamentos"),
                "value": brl(totals[k]),
                "link": f"/orcamento/{format_month(sample_months[k])}"
                if grouping in {"month", "week", "day"}
                else None,
            }
            for k in shown
        ],
        "links": [{"label": "Ver tendências", "to": "/analises?secao=tendencias"}],
        "suggestions": [],
    }


def _exec_avg(
    user: User,
    plan: QueryPlan,
    rows: list[_Record],
    period: PeriodSpec,
    about_txt: str,
    today: date,
) -> dict[str, Any]:
    total = sum((r.amount for r in rows), Decimal(0))
    grouping = plan.grouping or "month"
    if grouping in {"day", "week"}:
        d_start = period.day_start or cycle_range(period.start, user.month_start_day)[0]
        d_end = period.day_end or cycle_range(period.end, user.month_start_day)[1]
        days = max(1, (min(d_end, today) - d_start).days + 1)
        if grouping == "day":
            return {
                "intent": "per_day",
                "answer": f"{cap(period.label)}{about_txt}, a média foi de {brl(total / days)} por dia ({brl(total)} em {plural(days, 'dia', 'dias')}).",
                "items": [],
                "links": [],
                "suggestions": [],
            }
        weeks = max(Decimal(1), Decimal(days) / 7)
        return {
            "intent": "per_week",
            "answer": f"{cap(period.label)}{about_txt}, a média foi de {brl(total / weeks)} por semana ({brl(total)} em {plural(days, 'dia', 'dias')}).",
            "items": [],
            "links": [],
            "suggestions": [],
        }
    by_month: dict[date, Decimal] = defaultdict(Decimal)
    for r in rows:
        by_month[r.month] += r.amount
    avg_m = total / len(by_month)
    return {
        "intent": "average",
        "answer": f"{cap(period.label)}{about_txt}, a média foi de {brl(avg_m)} por mês ({brl(total)} em {plural(len(by_month), 'mês', 'meses')} com lançamento).",
        "items": [
            {
                "label": cap(month_label(m)),
                "detail": None,
                "value": brl(v),
                "link": f"/orcamento/{format_month(m)}",
            }
            for m, v in sorted(by_month.items())[-6:]
        ],
        "links": [],
        "suggestions": [],
    }


def _exec_sum(
    plan: QueryPlan,
    rows: list[_Record],
    period: PeriodSpec,
    about_txt: str,
    index: UserEntityIndex,
) -> dict[str, Any]:
    f = plan.filters
    total = sum((r.amount for r in rows), Decimal(0))
    verb = "recebeu" if plan.domain == "income" else "gastou"
    answer_txt = f"{cap(period.label)} você {verb} {brl(total)}{about_txt}, em {plural(len(rows), 'lançamento', 'lançamentos')}."
    if not period.single:
        months_count = len({r.month for r in rows})
        answer_txt += f" Média de {brl(total / months_count)} por mês com registro."
    top_rows = sorted(rows, key=lambda r: r.amount, reverse=True)[: plan.limit]
    intent_out = (
        "incomes"
        if plan.domain == "income"
        and not (f.text_terms or f.category_ids or f.account_ids or f.mei)
        else "sum"
    )
    return {
        "intent": intent_out,
        "answer": answer_txt,
        "items": [_record_item(r, index) for r in top_rows],
        "links": [
            {"label": "Abrir o Orçamento", "to": f"/orcamento/{format_month(top_rows[0].month)}"}
        ],
        "suggestions": ["Qual foi o maior gasto?", "Qual ano mais gastei?"],
    }


def execute_analytic(
    db: Session,
    user: User,
    plan: QueryPlan,
    index: UserEntityIndex,
    today: date,
) -> dict[str, Any]:
    current = month_of(today, user.month_start_day)
    f = plan.filters
    period = _resolve_analytic_period(db, user, plan, index, today, current)
    about = _filter_summary(f)
    about_txt = f" {about}" if about else ""

    if plan.intent == "balance":
        return _exec_balance(db, user, f, period, about_txt, index, today)
    if plan.intent == "compare":
        return _exec_compare(db, user, plan, f, about_txt, index, today, current)

    rows = fetch_records(db, user, period, f, plan.domain, index, today)
    if not rows:
        if plan.intent == "percent" and plan.grouping == "of_income":
            all_inc = fetch_records(db, user, period, QueryFilters(), "income", index, today)
            if not all_inc:
                return {
                    "intent": "percent",
                    "answer": f"Não há receitas lançadas {period.label} para calcular o percentual.",
                    "items": [],
                    "links": [{"label": "Abrir o Orçamento", "to": "/orcamento"}],
                    "suggestions": [],
                }
        verb = "receitas" if plan.domain == "income" else "despesas"
        return {
            "intent": "empty",
            "answer": f"Não encontrei {verb}{about_txt} {period.label}.",
            "items": [],
            "links": [{"label": "Abrir o Orçamento", "to": "/orcamento"}],
            "suggestions": ["Qual ano mais gastei?", "O que mais gastei este mês?"],
        }

    row_handlers = {
        "percent": lambda: _exec_percent(db, user, plan, rows, period, about, index, today),
        "count": lambda: _exec_count(plan, rows, period, about_txt, index),
        "extreme_item": lambda: _exec_extreme_item(plan, rows, period, about_txt, index),
        "latest_item": lambda: _exec_latest_item(plan, rows, about_txt, index),
        "list_records": lambda: _exec_list_records(plan, rows, period, about_txt, index),
        "rank_group": lambda: _exec_rank_group(plan, rows, period, about_txt, index),
        "series": lambda: _exec_series(plan, rows, period, about_txt, index),
        "avg": lambda: _exec_avg(user, plan, rows, period, about_txt, today),
    }
    handler = row_handlers.get(plan.intent)
    return handler() if handler else _exec_sum(plan, rows, period, about_txt, index)
