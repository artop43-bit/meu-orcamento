"""Localizador universal ('onde está X lançamento / X gasto?'): busca ranqueada em todas as tabelas."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import case, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    Expense,
    Income,
    OtherDebt,
    PersonalLoan,
    PlannedExpense,
    RecurringItem,
    SplitShare,
    Transfer,
    User,
)
from app.services.bot.contracts import QueryPlan
from app.services.bot.lexicon import core
from app.services.bot.months import format_month, month_label, short_date, with_day
from app.services.bot.nlu.filters import UserEntityIndex
from app.services.bot.text_utils import (
    BM25Index,
    brl,
    cap,
    dice_trigram,
    normalize,
    plural,
    tokenize,
)

_LOCATE_STOP = core.COMMON_STOPWORDS | {
    "onde",
    "aonde",
    "cade",
    "esta",
    "ficam",
    "fica",
    "lancei",
    "cadastrei",
    "registrei",
    "anotei",
    "parar",
    "acha",
    "ache",
    "procura",
    "procure",
    "encontra",
    "encontre",
    "localiza",
    "localize",
    "aquele",
    "aquela",
    "qual",
    "mes",
    "mim",
    "pra",
}


@dataclass
class SearchDoc:
    kind: str
    title: str
    detail: str
    amount: Decimal | None
    when: date | None
    budget_month: date | None
    link: str
    tokens: list[str]
    norm_text: str
    category_id: uuid.UUID | None = None
    card_id: uuid.UUID | None = None
    account_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    payment_method: str | None = None
    person: str | None = None
    paid: bool | None = None


def _candidate_rows(
    db: Session, user: User, model: Any, plan: QueryPlan, query_tokens: list[str]
) -> list[Any]:
    """Só materializa candidatos, nunca todos os objetos do histórico para montar BM25.

    Prefixos curtos preservam a busca aproximada ("supermecado" → "supermercado").
    Se o SQL não encontrar nada, a reserva lê apenas texto/ID e normaliza acentos,
    sem carregar os objetos completos nem montar o índice de todo o histórico.
    """
    f = plan.filters
    query = select(model).where(model.user_id == user.id)
    if f.period and not f.period.all_time:
        if f.period.day_start and f.period.day_end:
            if model is Expense:
                from sqlalchemy import func

                when = func.coalesce(model.purchase_date, model.due_date, model.month)
                query = query.where(when.between(f.period.day_start, f.period.day_end))
            else:
                query = query.where(model.month.between(f.period.day_start, f.period.day_end))
        else:
            query = query.where(model.month.between(f.period.start, f.period.end))
    for field, values in (
        ("account_id", f.account_ids),
        ("project_id", f.project_ids),
    ):
        if values:
            if not hasattr(model, field):
                return []
            query = query.where(getattr(model, field).in_(values))
    if f.card_ids:
        if model is not Expense:
            return []
        query = query.where(or_(model.card_id.in_(f.card_ids), model.debit_card_id.in_(f.card_ids)))
    if f.paid is not None and model is Expense:
        query = query.where(model.paid == f.paid)
    if f.amount.target_amount is not None:
        target = f.amount.target_amount
        tolerance = max(Decimal("1.00"), target * f.amount.tolerance_pct)
        query = query.where(model.amount.between(target - tolerance, target + tolerance))
    else:
        if f.amount.min_amount is not None:
            query = query.where(model.amount >= f.amount.min_amount)
        if f.amount.max_amount is not None:
            query = query.where(model.amount <= f.amount.max_amount)

    terms = list(dict.fromkeys(token[:3] for token in query_tokens if len(token) >= 3))
    candidates = []
    if terms:
        matches = [
            column.ilike(f"%{term}%")
            for term in terms
            for column in (model.description, model.notes)
        ]
        # Categoria, cartão, conta e projeto também fazem parte do texto pesquisável.
        if model is Expense and f.category_ids:
            matches.append(model.category_id.in_(f.category_ids))
        if f.account_ids:
            matches.append(model.account_id.in_(f.account_ids))
        if f.project_ids and model is Expense:
            matches.append(model.project_id.in_(f.project_ids))
        if f.card_ids and model is Expense:
            matches.extend((model.card_id.in_(f.card_ids), model.debit_card_id.in_(f.card_ids)))
        if f.payment_methods and model is Expense:
            matches.append(model.payment_method.in_(f.payment_methods))
        relevance = sum(
            case((column.ilike(f"%{token}%"), 1), else_=0)
            for token in query_tokens
            for column in (model.description, model.notes)
        )
        candidates = list(
            db.scalars(
                query.where(or_(*matches)).order_by(relevance.desc(), model.month.desc()).limit(200)
            )
        )
        if not candidates:
            rows = db.execute(
                query.with_only_columns(model.id, model.description, model.notes)
            ).all()
            ids = []
            for row_id, description, notes in rows:
                tokens = tokenize(f"{description} {notes or ''}")
                if any(
                    qt in tokens
                    or any(
                        dt.startswith(qt) or (len(qt) >= 4 and dice_trigram(qt, dt) >= 0.55)
                        for dt in tokens
                    )
                    for qt in query_tokens
                ):
                    ids.append(row_id)
            if ids:
                candidates = list(
                    db.scalars(
                        query.where(model.id.in_(ids)).order_by(model.month.desc()).limit(200)
                    )
                )
    else:
        candidates = list(db.scalars(query.order_by(model.month.desc()).limit(200)))
    return candidates


def _docs_from_expenses(
    db: Session,
    user: User,
    plan: QueryPlan,
    query_tokens: list[str],
    cat_map: dict[uuid.UUID, str],
    card_map: dict[uuid.UUID, str],
    acc_map: dict[uuid.UUID, str],
    proj_map: dict[uuid.UUID, str],
) -> list[SearchDoc]:
    docs: list[SearchDoc] = []
    for e in _candidate_rows(db, user, Expense, plan, query_tokens):
        when = e.purchase_date or e.due_date or e.month
        cat = cat_map.get(e.category_id, "Sem categoria") if e.category_id else "Sem categoria"
        card = (
            card_map.get(e.card_id or e.debit_card_id) if (e.card_id or e.debit_card_id) else None
        )
        acc = acc_map.get(e.account_id) if e.account_id else None
        proj = proj_map.get(e.project_id) if e.project_id else None
        pay = core.PAYMENT_LABELS.get(e.payment_method or "", e.payment_method or "")
        parts = [f"Em {cap(month_label(e.month))}", short_date(when), cat]
        if pay:
            parts.append(pay)
        if card:
            parts.append(f"cartão {card}")
        elif acc:
            parts.append(acc)
        if proj:
            parts.append(f"projeto {proj}")
        if e.installment_number and e.installment_total:
            parts.append(f"parcela {e.installment_number}/{e.installment_total}")
        if not e.paid:
            parts.append("em aberto")
        raw_text = " ".join(
            x
            for x in (e.description, e.notes or "", cat, card or "", acc or "", proj or "", pay)
            if x
        )
        docs.append(
            SearchDoc(
                kind="expense",
                title=e.description,
                detail=" · ".join(parts),
                amount=e.amount,
                when=when,
                budget_month=e.month,
                link=f"/orcamento/{format_month(e.month)}",
                tokens=tokenize(raw_text),
                norm_text=normalize(raw_text),
                category_id=e.category_id,
                card_id=e.card_id or e.debit_card_id,
                account_id=e.account_id,
                project_id=e.project_id,
                payment_method=e.payment_method,
                paid=e.paid,
            )
        )
    return docs


def _docs_from_incomes(
    db: Session,
    user: User,
    plan: QueryPlan,
    query_tokens: list[str],
    acc_map: dict[uuid.UUID, str],
) -> list[SearchDoc]:
    docs: list[SearchDoc] = []
    for i in _candidate_rows(db, user, Income, plan, query_tokens):
        acc = acc_map.get(i.account_id) if i.account_id else None
        parts = [f"Receita em {cap(month_label(i.month))}"]
        if i.day:
            parts.append(f"dia {i.day}")
        if acc:
            parts.append(acc)
        if i.mei:
            parts.append("MEI")
        raw_text = " ".join(x for x in (i.description, i.notes or "", acc or "", "receita") if x)
        docs.append(
            SearchDoc(
                kind="income",
                title=i.description,
                detail=" · ".join(parts),
                amount=i.amount,
                when=i.month,
                budget_month=i.month,
                link=f"/orcamento/{format_month(i.month)}",
                tokens=tokenize(raw_text),
                norm_text=normalize(raw_text),
                account_id=i.account_id,
            )
        )
    return docs


def _docs_from_recurring_and_planned(
    db: Session,
    user: User,
    cat_map: dict[uuid.UUID, str],
    acc_map: dict[uuid.UUID, str],
) -> list[SearchDoc]:
    docs: list[SearchDoc] = []
    for r in db.scalars(select(RecurringItem).where(RecurringItem.user_id == user.id)):
        cat = cat_map.get(r.category_id) if r.category_id else None
        kind_label = "Receita fixa" if r.kind == "income" else "Despesa fixa"
        parts = [kind_label]
        if cat:
            parts.append(cat)
        if r.due_day:
            parts.append(f"dia {r.due_day}")
        raw_text = " ".join(x for x in (r.description, r.notes or "", cat or "", kind_label) if x)
        docs.append(
            SearchDoc(
                kind="recurring",
                title=r.description,
                detail=" · ".join(parts),
                amount=r.amount,
                when=r.start_month,
                budget_month=None,
                link="/ajustes/recorrencias",
                tokens=tokenize(raw_text),
                norm_text=normalize(raw_text),
                category_id=r.category_id,
                payment_method=r.payment_method,
            )
        )

    for t in db.scalars(select(Transfer).where(Transfer.user_id == user.id)):
        src = acc_map.get(t.from_account_id, "Conta")
        dst = acc_map.get(t.to_account_id, "Conta")
        raw_text = " ".join(x for x in ("transferencia", src, dst, t.notes or "") if x)
        docs.append(
            SearchDoc(
                kind="transfer",
                title=f"Transferência: {src} → {dst}",
                detail=f"Em {short_date(t.date)}" + (f" · {t.notes}" if t.notes else ""),
                amount=t.amount,
                when=t.date,
                budget_month=None,
                link="/contas",
                tokens=tokenize(raw_text),
                norm_text=normalize(raw_text),
            )
        )

    for p in db.scalars(select(PlannedExpense).where(PlannedExpense.user_id == user.id)):
        cat = cat_map.get(p.category_id) if p.category_id else None
        raw_text = " ".join(x for x in (p.description, p.notes or "", cat or "", "planejado") if x)
        docs.append(
            SearchDoc(
                kind="planned",
                title=p.description,
                detail=f"Planejado para {short_date(p.date)}" + (f" · {cat}" if cat else ""),
                amount=p.amount,
                when=p.date,
                budget_month=None,
                link="/calendario",
                tokens=tokenize(raw_text),
                norm_text=normalize(raw_text),
                category_id=p.category_id,
            )
        )
    return docs


def _docs_from_entities(db: Session, user: User, index: UserEntityIndex) -> list[SearchDoc]:
    docs: list[SearchDoc] = []
    for g in index.goals:
        raw_text = " ".join(x for x in (g.name, g.motivation or "", "meta") if x)
        docs.append(
            SearchDoc(
                kind="goal",
                title=f"Meta: {g.name}",
                detail=f"Guardado {brl(g.current_amount)} de {brl(g.target_amount)}",
                amount=g.target_amount,
                when=g.target_date,
                budget_month=None,
                link="/metas",
                tokens=tokenize(raw_text),
                norm_text=normalize(raw_text),
            )
        )

    for l_item in index.loans:
        raw_text = " ".join(
            x
            for x in (l_item.name, l_item.institution or "", l_item.notes or "", "financiamento")
            if x
        )
        docs.append(
            SearchDoc(
                kind="loan",
                title=f"Financiamento: {l_item.name}",
                detail=f"{l_item.installments} parcelas · {l_item.institution or 'contrato'}",
                amount=l_item.principal,
                when=l_item.first_due,
                budget_month=None,
                link="/dividas",
                tokens=tokenize(raw_text),
                norm_text=normalize(raw_text),
            )
        )

    for d in db.scalars(select(OtherDebt).where(OtherDebt.user_id == user.id)):
        raw_text = " ".join(x for x in (d.name, d.notes or "", "divida") if x)
        docs.append(
            SearchDoc(
                kind="loan",
                title=f"Dívida: {d.name}",
                detail="Outras dívidas",
                amount=d.balance,
                when=None,
                budget_month=None,
                link="/dividas",
                tokens=tokenize(raw_text),
                norm_text=normalize(raw_text),
            )
        )

    for pl in db.scalars(select(PersonalLoan).where(PersonalLoan.user_id == user.id)):
        who = "te deve" if pl.direction == "owes_me" else "você deve"
        raw_text = " ".join(x for x in (pl.person, pl.description or "", "emprestimo divisao") if x)
        docs.append(
            SearchDoc(
                kind="friend_loan",
                title=f"{pl.person} ({pl.description or 'Empréstimo'})",
                detail=f"Divisões · {who} · início {short_date(pl.first_due)}",
                amount=pl.principal,
                when=pl.first_due,
                budget_month=None,
                link="/divisoes",
                tokens=tokenize(raw_text),
                norm_text=normalize(raw_text),
                person=pl.person,
            )
        )

    for s in db.scalars(select(SplitShare).where(SplitShare.user_id == user.id)):
        who = "te deve" if s.direction == "owes_me" else "você deve"
        raw_text = " ".join(x for x in (s.person, s.description, "divisao") if x)
        docs.append(
            SearchDoc(
                kind="friend_loan",
                title=f"{s.person}: {s.description}",
                detail=f"Divisões · {who}",
                amount=s.amount,
                when=s.created_at.astimezone(ZoneInfo(get_settings().timezone)).date()
                if s.created_at
                else None,
                budget_month=None,
                link="/divisoes",
                tokens=tokenize(raw_text),
                norm_text=normalize(raw_text),
                person=s.person,
            )
        )

    for inv in index.investments:
        raw_text = " ".join(
            x
            for x in (
                inv.name,
                inv.ticker or "",
                inv.institution or "",
                inv.notes or "",
                "investimento",
            )
            if x
        )
        docs.append(
            SearchDoc(
                kind="investment",
                title=f"Investimento: {inv.name}",
                detail=inv.institution or inv.kind,
                amount=inv.current_value,
                when=None,
                budget_month=None,
                link="/investimentos",
                tokens=tokenize(raw_text),
                norm_text=normalize(raw_text),
            )
        )

    for proj in index.projects:
        raw_text = f"projeto {proj.name}"
        docs.append(
            SearchDoc(
                kind="project",
                title=f"Projeto: {proj.name}",
                detail="Projetos e etiquetas",
                amount=proj.budget,
                when=None,
                budget_month=None,
                link="/orcamento",
                tokens=tokenize(raw_text),
                norm_text=normalize(raw_text),
                project_id=proj.id,
            )
        )
    return docs


def _build_docs(
    db: Session, user: User, index: UserEntityIndex, plan: QueryPlan, query_tokens: list[str]
) -> list[SearchDoc]:
    cat_map = {c.id: c.name for c in index.categories}
    card_map = {c.id: c.name for c in index.cards}
    acc_map = {a.id: a.name for a in index.accounts}
    proj_map = {p.id: p.name for p in index.projects}

    return [
        *_docs_from_expenses(db, user, plan, query_tokens, cat_map, card_map, acc_map, proj_map),
        *_docs_from_incomes(db, user, plan, query_tokens, acc_map),
        *_docs_from_recurring_and_planned(db, user, cat_map, acc_map),
        *_docs_from_entities(db, user, index),
    ]


def locate_records(
    db: Session, user: User, plan: QueryPlan, index: UserEntityIndex
) -> dict[str, Any]:
    f = plan.filters
    raw_tokens = [
        t for t in tokenize(plan.corrected_question) if t not in _LOCATE_STOP and len(t) >= 2
    ]
    query_tokens = list(dict.fromkeys([*f.text_terms, *raw_tokens]))
    query_tokens = [
        t
        for t in query_tokens
        if not (t.isdigit() and (2000 <= int(t) <= 2100 or f.amount.target_amount is not None))
    ]
    docs = _build_docs(db, user, index, plan, query_tokens)

    bm25 = BM25Index([d.tokens for d in docs])
    scored: list[tuple[float, SearchDoc]] = []

    for idx, doc in enumerate(docs):
        if f.period is not None:
            if f.period.day_start and f.period.day_end:
                if doc.when is None or not (f.period.day_start <= doc.when <= f.period.day_end):
                    continue
            elif doc.budget_month is not None:
                if not (f.period.start <= doc.budget_month <= f.period.end):
                    continue
            elif doc.when is not None:
                if not (f.period.start <= doc.when <= with_day(f.period.end, 31)):
                    continue

        if f.card_ids and doc.card_id not in f.card_ids:
            continue
        if f.account_ids and doc.account_id not in f.account_ids:
            continue
        if f.project_ids and doc.project_id not in f.project_ids:
            continue
        if f.payment_methods and doc.payment_method not in f.payment_methods:
            if not any(pm in doc.norm_text for pm in f.payment_methods):
                continue
        if f.paid is not None and doc.paid is not None and doc.paid != f.paid:
            continue
        if f.people and (doc.person is None or doc.person not in f.people):
            continue

        amount_bonus = 0.0
        if f.amount.target_amount is not None:
            if doc.amount is None or not f.amount.matches(doc.amount):
                continue
            diff = abs(doc.amount - f.amount.target_amount)
            amount_bonus = 8.0 if diff == 0 else max(2.0, 6.0 - float(diff) * 0.2)
        elif f.amount.min_amount is not None or f.amount.max_amount is not None:
            if doc.amount is None or not f.amount.matches(doc.amount):
                continue
            amount_bonus = 2.0

        text_score = bm25.score(query_tokens, idx) if query_tokens else 0.0
        if query_tokens:
            phrase = " ".join(query_tokens)
            if f" {phrase} " in f" {doc.norm_text} ":
                text_score += 5.0
            for qt in query_tokens:
                if qt in doc.tokens or (
                    len(qt) >= 4 and any(dt.startswith(qt) for dt in doc.tokens)
                ):
                    text_score += 2.0
                elif len(qt) >= 4:
                    best_fuzzy = max((dice_trigram(qt, dt) for dt in doc.tokens), default=0.0)
                    if best_fuzzy >= 0.55:
                        text_score += best_fuzzy * 2.5

        cat_bonus = 2.0 if (f.category_ids and doc.category_id in f.category_ids) else 0.0
        total_score = text_score + amount_bonus + cat_bonus

        if query_tokens and text_score < 0.8 and amount_bonus == 0 and cat_bonus == 0:
            continue
        if not query_tokens and not (f.has_data_filters() or f.period is not None):
            continue

        scored.append((total_score, doc))

    scored.sort(
        key=lambda pair: (
            -round(pair[0], 3),
            -(pair[1].when.toordinal() if pair[1].when else 0),
        )
    )

    if not scored:
        return {
            "intent": "locate_record",
            "answer": "Não encontrei nenhum lançamento ou registro com essas características.",
            "items": [],
            "links": [
                {"label": "Abrir a busca completa", "to": "/busca"},
                {"label": "Ver o Orçamento", "to": "/orcamento"},
            ],
            "suggestions": [
                "O que lancei este mês?",
                "Onde encontro as recorrências?",
            ],
        }

    top_docs = [doc for _, doc in scored[: plan.limit]]
    first = top_docs[0]
    where = (
        f"no orçamento de {month_label(first.budget_month)}"
        if first.budget_month
        else f"em {first.link}"
    )
    amount_txt = f" ({brl(first.amount)})" if first.amount is not None else ""
    if len(scored) == 1:
        answer = f"Encontrei 1 registro: {first.title}{amount_txt} está {where} — {first.detail}."
    else:
        answer = (
            f"Encontrei {plural(len(scored), 'registro parecido', 'registros parecidos')}. "
            f"O mais próximo é {first.title}{amount_txt}, {where} ({first.detail})."
        )

    return {
        "intent": "locate_record",
        "answer": answer,
        "items": [
            {
                "label": d.title,
                "detail": d.detail,
                "value": brl(d.amount) if d.amount is not None else None,
                "link": d.link,
            }
            for d in top_docs
        ],
        "links": [{"label": f"Abrir {first.title[:30]}", "to": first.link}],
        "suggestions": [
            "Qual foi meu maior lançamento?",
            "Quanto gastei com isso este ano?",
        ],
    }
