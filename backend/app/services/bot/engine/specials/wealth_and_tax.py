"""Consultas especializadas de contas, investimentos, dívidas, divisões, metas, IR e MEI."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Challenge,
    Expense,
    Goal,
    Income,
    Investment,
    Loan,
    MoneyAccount,
    NetWorthSnapshot,
    OtherDebt,
    Transfer,
    User,
)
from app.services import goals, loans, splits
from app.services.bot.contracts import QueryPlan
from app.services.bot.months import format_month, month_label, short_date, with_day
from app.services.bot.nlu.filters import UserEntityIndex
from app.services.bot.text_utils import brl, normalize, pct, plural, signed_brl


def loans_summary(db: Session, user: User) -> dict[str, Any]:
    loan_rows = list(db.scalars(select(Loan).where(Loan.user_id == user.id)))
    debt_rows = list(db.scalars(select(OtherDebt).where(OtherDebt.user_id == user.id)))
    if not loan_rows and not debt_rows:
        return {
            "intent": "loans",
            "answer": "Você não tem financiamentos nem dívidas cadastradas.",
            "items": [],
            "links": [{"label": "Abrir dívidas", "to": "/dividas"}],
            "suggestions": [],
        }
    items = []
    total = Decimal(0)
    for l_item in loan_rows:
        summary = loans.summary(db, l_item)
        paid_count = summary["paid_installments"]
        est_balance = summary["balance"]
        total += est_balance
        items.append(
            {
                "label": l_item.name,
                "detail": f"{paid_count}/{l_item.installments} parcelas pagas · {l_item.institution or l_item.system.upper()}",
                "value": brl(est_balance),
                "link": "/dividas",
            }
        )
    for d in debt_rows:
        total += d.balance
        items.append(
            {"label": d.name, "detail": "outra dívida", "value": brl(d.balance), "link": "/dividas"}
        )
    return {
        "intent": "loans",
        "answer": f"O saldo devedor estimado é de {brl(total)} em {plural(len(items), 'contrato', 'contratos')}.",
        "items": items[:6],
        "links": [{"label": "Abrir dívidas", "to": "/dividas"}],
        "suggestions": [],
    }


def friend_loans_summary(db: Session, user: User, plan: QueryPlan) -> dict[str, Any]:
    board = splits.board(db, user)
    person_balances: dict[str, Decimal] = {}
    person_display: dict[str, str] = {}
    splits_list = []
    for person in board["people"]:
        key = normalize(person["person"])
        person_display[key] = person["person"]
        person_balances[key] = person_balances.get(key, Decimal(0)) + person["balance"]
        splits_list.extend(person["items"])
    profit_received = board["loans"]["profit_received"]
    profit_expected = board["loans"]["profit_expected"]
    lent_count = board["loans"]["lent_count"]
    if not board["people"]:
        return {
            "intent": "friend_loans",
            "answer": "Ninguém te deve e você não deve a ninguém nas Divisões.",
            "items": [],
            "links": [{"label": "Abrir divisões", "to": "/divisoes"}],
            "suggestions": [],
        }

    if not plan.filters.people and re.search(r"\blucr|\bjuros|\brend", plan.corrected_question):
        return {
            "intent": "friend_loans",
            "answer": f"Você já recebeu {brl(profit_received)} de juros com empréstimos; nos {plural(lent_count, 'empréstimo', 'empréstimos')} ativos ainda há {brl(profit_expected)} previstos de juros.",
            "items": [],
            "links": [{"label": "Abrir divisões", "to": "/divisoes"}],
            "suggestions": [],
        }

    if plan.filters.people:
        person = plan.filters.people[0]
        pkey = normalize(person)
        display_name = person_display.get(pkey, person)
        bal = person_balances.get(pkey, Decimal(0))
        if bal > 0:
            msg = f"{display_name} ainda te deve {brl(bal)}."
        elif bal < 0:
            msg = f"Você ainda deve {brl(-bal)} a {display_name}."
        else:
            msg = f"Você e {display_name} estão quites."
        return {
            "intent": "friend_loans",
            "answer": msg,
            "items": [
                {
                    "label": s.description,
                    "detail": "te deve" if s.direction == "owes_me" else "você deve",
                    "value": brl(s.amount),
                    "link": "/divisoes",
                }
                for s in splits_list
                if normalize(s.person) == pkey
            ],
            "links": [{"label": "Abrir divisões", "to": "/divisoes"}],
            "suggestions": [],
        }

    owed_to_me = sum((v for v in person_balances.values() if v > 0), Decimal(0))
    i_owe = sum((-v for v in person_balances.values() if v < 0), Decimal(0))
    items = [
        {
            "label": person_display.get(pkey, pkey),
            "detail": "te deve" if val > 0 else "você deve" if val < 0 else "quites",
            "value": brl(abs(val)),
            "link": "/divisoes",
        }
        for pkey, val in sorted(person_balances.items(), key=lambda kv: -abs(kv[1]))
    ]
    if i_owe == 0:
        summary = f"Te devem {brl(owed_to_me)} nas Divisões."
    else:
        summary = f"Te devem {brl(owed_to_me)} no total e você deve {brl(i_owe)} nas Divisões."
    return {
        "intent": "friend_loans",
        "answer": summary,
        "items": items[:6],
        "links": [{"label": "Abrir divisões", "to": "/divisoes"}],
        "suggestions": [],
    }


def investments_summary(db: Session, user: User) -> dict[str, Any]:
    rows = list(db.scalars(select(Investment).where(Investment.user_id == user.id)))
    if not rows:
        return {
            "intent": "investments",
            "answer": "Você ainda não cadastrou investimentos.",
            "items": [],
            "links": [{"label": "Abrir investimentos", "to": "/investimentos"}],
            "suggestions": [],
        }
    invested = sum((r.invested_amount for r in rows), Decimal(0))
    current_val = sum((r.current_value for r in rows), Decimal(0))
    gain = current_val - invested
    rows.sort(key=lambda r: -r.current_value)
    return {
        "intent": "investments",
        "answer": f"Você tem {brl(current_val)} investidos (aplicou {brl(invested)}). O resultado acumulado é de {('+' if gain >= 0 else '−')}{brl(gain)}.",
        "items": [
            {
                "label": r.name,
                "detail": f"{r.institution or r.kind}"
                + (" · reserva" if r.is_emergency_reserve else ""),
                "value": brl(r.current_value),
                "link": "/investimentos",
            }
            for r in rows[:6]
        ],
        "links": [{"label": "Abrir investimentos", "to": "/investimentos"}],
        "suggestions": [],
    }


def accounts_summary(db: Session, user: User, plan: QueryPlan) -> dict[str, Any]:
    accs = list(
        db.scalars(
            select(MoneyAccount).where(
                MoneyAccount.user_id == user.id, MoneyAccount.archived.is_(False)
            )
        )
    )
    if plan.filters.account_ids:
        accs = [a for a in accs if a.id in plan.filters.account_ids]
    if not accs:
        return {
            "intent": "accounts",
            "answer": "Você não tem contas cadastradas para esse filtro.",
            "items": [],
            "links": [{"label": "Abrir contas", "to": "/contas"}],
            "suggestions": [],
        }
    incomes = list(db.scalars(select(Income).where(Income.user_id == user.id)))
    expenses = list(
        db.scalars(select(Expense).where(Expense.user_id == user.id, Expense.paid.is_(True)))
    )
    transfers = list(db.scalars(select(Transfer).where(Transfer.user_id == user.id)))

    items = []
    total_bal = Decimal(0)
    for a in accs:
        bal = a.initial_balance
        bal += sum((i.amount for i in incomes if i.account_id == a.id), Decimal(0))
        bal -= sum(
            (e.amount for e in expenses if e.account_id == a.id and e.card_id is None), Decimal(0)
        )
        bal += sum((t.amount for t in transfers if t.to_account_id == a.id), Decimal(0))
        bal -= sum((t.amount for t in transfers if t.from_account_id == a.id), Decimal(0))
        total_bal += bal
        items.append(
            {"label": a.name, "detail": a.kind, "value": signed_brl(bal), "link": "/contas"}
        )

    return {
        "intent": "accounts",
        "answer": f"O saldo somado em {plural(len(accs), 'conta', 'contas')} é de {signed_brl(total_bal)}.",
        "items": items,
        "links": [{"label": "Abrir contas", "to": "/contas"}],
        "suggestions": [],
    }


def transfers_summary(
    db: Session, user: User, plan: QueryPlan, index: UserEntityIndex
) -> dict[str, Any]:
    rows = list(
        db.scalars(
            select(Transfer).where(Transfer.user_id == user.id).order_by(Transfer.date.desc())
        )
    )
    if plan.filters.account_ids:
        rows = [
            t
            for t in rows
            if t.from_account_id in plan.filters.account_ids
            or t.to_account_id in plan.filters.account_ids
        ]
    if plan.filters.period is not None and not plan.filters.period.all_time:
        p = plan.filters.period
        d_start = p.day_start or p.start
        d_end = p.day_end or with_day(p.end, 31)
        rows = [t for t in rows if d_start <= t.date <= d_end]
    if not rows:
        return {
            "intent": "transfers",
            "answer": "Não encontrei transferências entre contas nesse recorte.",
            "items": [],
            "links": [{"label": "Abrir contas", "to": "/contas"}],
            "suggestions": [],
        }
    acc_map = {a.id: a.name for a in index.accounts}
    total = sum((t.amount for t in rows), Decimal(0))
    return {
        "intent": "transfers",
        "answer": f"Encontrei {plural(len(rows), 'transferência', 'transferências')} entre contas, somando {brl(total)}.",
        "items": [
            {
                "label": f"{acc_map.get(t.from_account_id, 'Conta')} → {acc_map.get(t.to_account_id, 'Conta')}",
                "detail": short_date(t.date) + (f" · {t.notes}" if t.notes else ""),
                "value": brl(t.amount),
                "link": "/contas",
            }
            for t in rows[:6]
        ],
        "links": [{"label": "Abrir contas", "to": "/contas"}],
        "suggestions": [],
    }


def goals_summary(db: Session, user: User, today: date | None = None) -> dict[str, Any]:
    rows = list(
        db.scalars(select(Goal).where(Goal.user_id == user.id).order_by(Goal.is_main.desc()))
    )
    if not rows:
        return {
            "intent": "goals",
            "answer": "Você ainda não cadastrou metas.",
            "items": [],
            "links": [{"label": "Criar meta", "to": "/metas"}],
            "suggestions": [],
        }
    items = []
    for g in rows[:5]:
        projection = goals.projection(db, user, g, today)
        rem = projection["remaining"]
        detail = (
            "concluída"
            if rem == 0
            else f"faltam {brl(rem)} · {pct(g.current_amount, g.target_amount)}"
        )
        if projection.get("eta"):
            detail += f" · previsão {month_label(projection['eta'])}"
        elif projection.get("required_monthly"):
            detail += f" · guardar {brl(projection['required_monthly'])} por mês"
        items.append(
            {"label": g.name, "detail": detail, "value": brl(g.current_amount), "link": "/metas"}
        )
    first = rows[0]
    rem0 = max(Decimal(0), first.target_amount - first.current_amount)
    return {
        "intent": "goals",
        "answer": f"Na sua meta principal ({first.name}), já guardou {brl(first.current_amount)} de {brl(first.target_amount)} (faltam {brl(rem0)}).",
        "items": items,
        "links": [{"label": "Abrir metas", "to": "/metas"}],
        "suggestions": [],
    }


def challenges_summary(db: Session, user: User) -> dict[str, Any]:
    rows = list(db.scalars(select(Challenge).where(Challenge.user_id == user.id)))
    if not rows:
        return {
            "intent": "challenges",
            "answer": "Você não tem desafios cadastrados.",
            "items": [],
            "links": [{"label": "Abrir desafios", "to": "/metas"}],
            "suggestions": [],
        }
    return {
        "intent": "challenges",
        "answer": f"Você tem {plural(len(rows), 'desafio', 'desafios')} registrado(s).",
        "items": [
            {
                "label": c.title,
                "detail": f"{c.days} dias · início {short_date(c.start_date)}"
                + (f" · {c.result}" if c.result else " · em andamento"),
                "value": brl(c.max_amount) if c.max_amount else None,
                "link": "/metas",
            }
            for c in rows[:5]
        ],
        "links": [{"label": "Abrir desafios", "to": "/metas"}],
        "suggestions": [],
    }


def tax_deductible_summary(
    db: Session, user: User, plan: QueryPlan, index: UserEntityIndex, today: date
) -> dict[str, Any]:
    ded_cats = [c for c in index.categories if c.deductible]
    if plan.filters.deductible and plan.filters.deductible != "any":
        ded_cats = [c for c in ded_cats if c.deductible == plan.filters.deductible]
    if not ded_cats:
        return {
            "intent": "tax_deductible",
            "answer": "Nenhuma categoria está marcada como dedutível no Imposto de Renda.",
            "items": [],
            "links": [{"label": "Configurar categorias", "to": "/ajustes/categorias"}],
            "suggestions": [],
        }
    year = plan.filters.period.start.year if plan.filters.period else today.year
    rows = list(
        db.scalars(
            select(Expense).where(
                Expense.user_id == user.id,
                Expense.category_id.in_([c.id for c in ded_cats]),
                Expense.month.between(date(year, 1, 1), date(year, 12, 1)),
            )
        )
    )
    total = sum((e.amount for e in rows), Decimal(0))
    by_cat: dict[str, Decimal] = defaultdict(Decimal)
    cat_names = {c.id: f"{c.name} ({c.deductible})" for c in ded_cats}
    for e in rows:
        if e.category_id is not None and e.category_id in cat_names:
            by_cat[cat_names[e.category_id]] += e.amount
    return {
        "intent": "tax_deductible",
        "answer": f"Em {year}, suas despesas dedutíveis no IR somam {brl(total)} em {plural(len(rows), 'lançamento', 'lançamentos')}.",
        "items": [
            {"label": k, "detail": None, "value": brl(v), "link": "/ajustes/categorias"}
            for k, v in sorted(by_cat.items(), key=lambda kv: -kv[1])
        ],
        "links": [{"label": "Ver categorias", "to": "/ajustes/categorias"}],
        "suggestions": [],
    }


def mei_summary(db: Session, user: User, plan: QueryPlan, today: date) -> dict[str, Any]:
    year = plan.filters.period.start.year if plan.filters.period else today.year
    rows = list(
        db.scalars(
            select(Income).where(
                Income.user_id == user.id,
                Income.mei.is_(True),
                Income.month.between(date(year, 1, 1), date(year, 12, 1)),
            )
        )
    )
    total = sum((i.amount for i in rows), Decimal(0))
    limit = getattr(user, "mei_annual_limit", None) or Decimal("81000.00")
    remaining = limit - total
    return {
        "intent": "mei",
        "answer": f"Em {year}, seu faturamento MEI registrado é de {brl(total)} ({pct(total, limit)} do teto anual de {brl(limit)}). Ainda restam {brl(max(Decimal(0), remaining))} dentro do limite.",
        "items": [
            {
                "label": i.description,
                "detail": month_label(i.month),
                "value": brl(i.amount),
                "link": f"/orcamento/{format_month(i.month)}",
            }
            for i in rows[:6]
        ],
        "links": [{"label": "Ver receitas", "to": "/orcamento"}],
        "suggestions": [],
    }


def net_worth_summary(db: Session, user: User) -> dict[str, Any]:
    snap = db.scalar(
        select(NetWorthSnapshot)
        .where(NetWorthSnapshot.user_id == user.id)
        .order_by(NetWorthSnapshot.month.desc())
        .limit(1)
    )
    if snap:
        nw = snap.assets - snap.debts
        return {
            "intent": "net_worth",
            "answer": f"No último registro ({month_label(snap.month)}), seu patrimônio líquido era {signed_brl(nw)} ({brl(snap.assets)} em bens/investimentos e {brl(snap.debts)} em dívidas).",
            "items": [
                {
                    "label": "Ativos",
                    "detail": None,
                    "value": brl(snap.assets),
                    "link": "/investimentos",
                },
                {"label": "Dívidas", "detail": None, "value": brl(snap.debts), "link": "/dividas"},
                {
                    "label": "Patrimônio líquido",
                    "detail": None,
                    "value": signed_brl(nw),
                    "link": "/analises",
                },
            ],
            "links": [{"label": "Abrir patrimônio", "to": "/analises?secao=patrimonio"}],
            "suggestions": [],
        }
    return investments_summary(db, user)
