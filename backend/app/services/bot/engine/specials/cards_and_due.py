"""Consultas especializadas de cartões de crédito, faturas, vencimentos e parcelas."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CreditCard, Expense, User
from app.services import cards
from app.services.bot.contracts import QueryPlan
from app.services.bot.months import format_month, month_label, month_of, short_date
from app.services.bot.nlu.filters import UserEntityIndex
from app.services.bot.text_utils import brl, cap, normalize, plural


def cards_summary(db: Session, user: User, plan: QueryPlan, today: date) -> dict[str, Any]:
    cards_list = list(db.scalars(select(CreditCard).where(CreditCard.user_id == user.id)))
    if plan.filters.card_ids:
        cards_list = [c for c in cards_list if c.id in plan.filters.card_ids]
    if not cards_list:
        return {
            "intent": "cards",
            "answer": "Você ainda não cadastrou cartão de crédito.",
            "items": [],
            "links": [{"label": "Cadastrar cartão", "to": "/cartoes"}],
            "suggestions": [],
        }

    unpaid = list(
        db.scalars(
            select(Expense).where(
                Expense.user_id == user.id,
                Expense.card_id.is_not(None),
                Expense.paid.is_(False),
            )
        )
    )
    items = []
    total_used = Decimal(0)
    for c in cards_list:
        used = sum((e.amount for e in unpaid if e.card_id == c.id), Decimal(0))
        total_used += used
        detail_parts = []
        if c.limit_amount is not None:
            avail = c.limit_amount - used
            detail_parts.append(f"disponível {brl(avail)} de {brl(c.limit_amount)}")
        if c.closing_day and c.due_day:
            detail_parts.append(f"fecha dia {c.closing_day} · vence dia {c.due_day}")
        items.append(
            {
                "label": c.name,
                "detail": " · ".join(detail_parts) or c.kind,
                "value": brl(used),
                "link": "/cartoes",
            }
        )
    return {
        "intent": "cards",
        "answer": f"Você tem {brl(total_used)} em compras ainda não pagas em {plural(len(cards_list), 'cartão', 'cartões')}.",
        "items": items,
        "links": [{"label": "Abrir cartões", "to": "/cartoes"}],
        "suggestions": ["Qual fatura vence primeiro?"],
    }


def invoices_summary(db: Session, user: User, plan: QueryPlan, today: date) -> dict[str, Any]:
    cards_list = [
        c
        for c in db.scalars(select(CreditCard).where(CreditCard.user_id == user.id))
        if c.kind in {"credit", "both"}
    ]
    if plan.filters.card_ids:
        cards_list = [c for c in cards_list if c.id in plan.filters.card_ids]
    if not cards_list:
        return {
            "intent": "cards",
            "answer": "Você ainda não cadastrou cartão de crédito.",
            "items": [],
            "links": [{"label": "Abrir cartões", "to": "/cartoes"}],
            "suggestions": [],
        }

    rows: list[tuple[date, str, Decimal, date]] = []
    for card in cards_list:
        # Cada mês representa uma fatura real; não misture parcelas de meses diferentes.
        months = db.scalars(
            select(Expense.month)
            .where(
                Expense.user_id == user.id,
                Expense.card_id == card.id,
                Expense.paid.is_(False),
            )
            .distinct()
        )
        for month in months:
            inv = cards.invoice(db, card, month, today)
            if inv["status"] != "paid" and inv["total"] > inv["paid_total"]:
                rows.append((inv["due_date"], card.name, inv["total"], inv["closing_date"]))
    if not rows:
        return {
            "intent": "invoices",
            "answer": "Nenhuma fatura em aberto no momento.",
            "items": [],
            "links": [{"label": "Abrir cartões", "to": "/cartoes"}],
            "suggestions": [],
        }
    rows.sort(key=lambda r: r[0])
    due_dt, name, val, close_dt = rows[0]
    return {
        "intent": "invoices",
        "answer": f"A próxima fatura é a do {name}: {brl(val)}, vence em {short_date(due_dt)} (fecha em {short_date(close_dt)}).",
        "items": [
            {
                "label": n,
                "detail": f"fecha {short_date(cl)} · vence {short_date(du)}",
                "value": brl(v),
                "link": "/cartoes",
            }
            for du, n, v, cl in rows[:6]
        ],
        "links": [{"label": "Abrir cartões", "to": "/cartoes"}],
        "suggestions": [],
    }


def due_summary(db: Session, user: User, plan: QueryPlan, today: date) -> dict[str, Any]:
    only_late = plan.filters.overdue is True
    until = today + timedelta(days=10)
    rows = list(
        db.scalars(
            select(Expense)
            .where(
                Expense.user_id == user.id,
                Expense.paid.is_(False),
                Expense.due_date.is_not(None),
                Expense.due_date <= until,
            )
            .order_by(Expense.due_date)
        )
    )
    late = [e for e in rows if e.due_date and e.due_date < today]
    soon = [] if only_late else [e for e in rows if e.due_date and e.due_date >= today]

    if only_late and not late:
        return {
            "intent": "due",
            "answer": "Nenhuma conta atrasada.",
            "items": [],
            "links": [{"label": "Abrir o calendário", "to": "/calendario"}],
            "suggestions": [],
        }
    if not late and not soon:
        return {
            "intent": "due",
            "answer": "Nada vencendo nos próximos 10 dias e nenhuma conta atrasada.",
            "items": [],
            "links": [{"label": "Abrir o calendário", "to": "/calendario"}],
            "suggestions": [],
        }
    parts = []
    if soon:
        parts.append(
            f"{plural(len(soon), 'conta vence', 'contas vencem')} nos próximos 10 dias ({brl(sum((e.amount for e in soon), Decimal(0)))})"
        )
    if late:
        parts.append(
            f"{plural(len(late), 'conta está atrasada', 'contas estão atrasadas')} ({brl(sum((e.amount for e in late), Decimal(0)))})"
        )
    items = [
        {
            "label": e.description,
            "detail": (
                ("atrasada · " if e.due_date and e.due_date < today else "")
                + f"vence {short_date(e.due_date)}"
            )
            if e.due_date
            else "",
            "value": brl(e.amount),
            "link": f"/orcamento/{format_month(e.month)}",
        }
        for e in (late + soon)[:8]
    ]
    return {
        "intent": "due",
        "answer": cap(" e ".join(parts)) + ".",
        "items": items,
        "links": [{"label": "Abrir o calendário", "to": "/calendario"}],
        "suggestions": [],
    }


def installments_summary(
    db: Session, user: User, plan: QueryPlan, index: UserEntityIndex, today: date
) -> dict[str, Any]:
    current = month_of(today, user.month_start_day)
    rows = list(
        db.scalars(
            select(Expense).where(
                Expense.user_id == user.id,
                Expense.installment_group_id.is_not(None),
                Expense.month >= current,
                Expense.paid.is_(False),
            )
        )
    )
    if plan.filters.card_ids:
        rows = [e for e in rows if e.card_id in plan.filters.card_ids]
    if plan.filters.category_ids:
        rows = [e for e in rows if e.category_id in plan.filters.category_ids]
    if plan.filters.text_terms:
        rows = [
            e
            for e in rows
            if all(
                t in normalize(f"{e.description} {e.notes or ''}") for t in plan.filters.text_terms
            )
        ]
    if not rows:
        return {
            "intent": "installments",
            "answer": "Não há parcelas em aberto para esse filtro.",
            "items": [],
            "links": [],
            "suggestions": [],
        }
    groups: dict[Any, list[Expense]] = defaultdict(list)
    for e in rows:
        groups[e.installment_group_id].append(e)
    items = []
    total = Decimal(0)
    for grp in sorted(groups.values(), key=lambda g: -sum((e.amount for e in g), Decimal(0))):
        amt = sum((e.amount for e in grp), Decimal(0))
        total += amt
        last = max(grp, key=lambda e: e.month)
        name = re.sub(r"\s*\(?\d+\s*/\s*\d+\)?\s*$", "", grp[0].description)
        items.append(
            {
                "label": name,
                "detail": f"faltam {plural(len(grp), 'parcela', 'parcelas')} de {brl(grp[0].amount)} · até {month_label(last.month)}",
                "value": brl(amt),
                "link": f"/orcamento/{format_month(min(e.month for e in grp))}",
            }
        )
    first = items[0]
    text = (
        f"Você tem {len(items)} compras parceladas em aberto, somando {brl(total)}. A maior é {first['label']} ({first['detail']})."
        if len(items) > 1
        else f"{first['label']}: {first['detail']} ({first['value']} no total)."
    )
    return {
        "intent": "installments",
        "answer": text,
        "items": items[:6],
        "links": [],
        "suggestions": [],
    }
