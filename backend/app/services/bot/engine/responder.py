"""Orquestrador principal: planeja, executa e devolve o contrato AskOut com contexto e debug."""

from __future__ import annotations

import difflib
from datetime import date
from typing import Any
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.models import User
from app.services.bot.engine import executor, locator, specials
from app.services.bot.lexicon import intents
from app.services.bot.months import today_local
from app.services.bot.nlu.filters import UserEntityIndex, load_entity_index
from app.services.bot.nlu.planner import build_plan
from app.services.bot.text_utils import normalize

SUGGESTIONS = [
    "O que mais gastei este mês?",
    "Qual ano mais gastei?",
    "Qual foi meu maior gasto no ano?",
    "Onde está o lançamento da farmácia?",
    "Quanto gastei no Pix este mês?",
    "O que vence nos próximos dias?",
    "Onde encontro as recorrências?",
]

_KNOWN_PROMPTS = [
    "Quanto posso gastar hoje?",
    "O que mais gastei este mês?",
    "Qual ano mais gastei?",
    "Qual mês gastei mais este ano?",
    "Qual foi meu maior gasto no ano?",
    "Quanto gastei com mercado no mês passado?",
    "Quanto gastei no Pix este mês?",
    "Onde está o lançamento da farmácia?",
    "O que vence nos próximos dias?",
    "Quantas parcelas faltam?",
    "Como estão minhas metas?",
    "Onde encontro as recorrências?",
    "Qual o saldo das contas?",
    "Quanto sobrou este mês?",
    "Quanto recebi este mês?",
]


def _similar_prompts(question: str, limit: int = 3) -> list[str]:
    norm = normalize(question)
    if not norm:
        return []
    scored = [
        (difflib.SequenceMatcher(None, norm, normalize(prompt)).ratio(), prompt)
        for prompt in _KNOWN_PROMPTS
    ]
    scored.sort(key=lambda pair: -pair[0])
    return [prompt for score, prompt in scored[:limit] if score >= 0.45]


def _close_subjects(index: UserEntityIndex, term: str) -> list[str]:
    candidates: dict[str, str] = {}
    for c in index.categories:
        candidates[normalize(c.name)] = c.name
    for c in index.cards:
        candidates[normalize(c.name)] = c.name
    for p in index.projects:
        candidates[normalize(p.name)] = p.name
    for d in index.expense_descriptions:
        for w in normalize(d).split():
            if len(w) >= 4 and not w.isdigit():
                candidates.setdefault(w, w)
    close = difflib.get_close_matches(term, list(candidates), n=3, cutoff=0.68)
    return [candidates[k] for k in close]


def _entry_response(question: str, kind: str) -> dict[str, Any]:
    phrase = " ".join(question.split())[:200]
    if kind == "amount":
        return {
            "intent": "entry",
            "answer": (
                "Aqui eu só tiro dúvidas e localizo informações, não registro lançamentos. "
                "Para lançar, use o Lançamento rápido do Orçamento (a sua frase já vai preenchida)."
            ),
            "items": [],
            "links": [
                {"label": "Abrir o Lançamento rápido", "to": f"/orcamento?lancar={quote(phrase)}"}
            ],
            "suggestions": ["Quanto gastei hoje?", "Qual foi meu último lançamento?"],
        }
    return {
        "intent": "entry",
        "answer": (
            "Aqui eu só tiro dúvidas, não registro lançamentos. "
            "Para lançar, use o Lançamento rápido do Orçamento."
        ),
        "items": [],
        "links": [{"label": "Abrir o Lançamento rápido", "to": "/orcamento?lancar="}],
        "suggestions": ["Quanto gastei hoje?", "Onde encontro as recorrências?"],
    }


def _pack_context(plan: Any) -> dict[str, Any]:
    f = plan.filters
    return {
        "intent": plan.intent,
        "domain": plan.domain,
        "grouping": plan.grouping,
        "order": plan.order,
        "period": f.period.dump() if f.period else None,
        "category_names": f.category_names,
        "card_names": f.card_names,
        "account_names": f.account_names,
        "project_names": f.project_names,
        "payment_methods": f.payment_methods,
        "text_terms": f.text_terms,
    }


_SIMPLE_INTENTS: dict[str, dict[str, Any]] = {
    "help": {
        "intent": "help",
        "answer": (
            "Olá! Pergunte qualquer coisa sobre seus dados cadastrados: gastos e receitas por período, "
            "cartão, conta, Pix/débito/crédito/boleto, projeto, valor aproximado ou faixa, "
            "localização exata de lançamentos ('onde está X?'), vencimentos, parcelas, metas, "
            "investimentos, financiamentos, divisões, IR e MEI — ou onde fica cada tela."
        ),
        "suggestions": SUGGESTIONS,
    },
    "thanks": {
        "intent": "thanks",
        "answer": "Por nada! Se precisar consultar ou localizar mais algum dado, é só perguntar.",
        "suggestions": SUGGESTIONS[:3],
    },
    "clarify": {
        "intent": "clarify",
        "answer": "Não entendi exatamente o que você quer consultar. Talvez você queira perguntar:",
        "suggestions": [
            "O que mais gastei este mês?",
            "Qual foi meu maior lançamento?",
            "Qual ano mais gastei?",
        ],
    },
}

_ANALYTIC_INTENTS = frozenset(
    {
        "sum",
        "count",
        "avg",
        "extreme_item",
        "latest_item",
        "rank_group",
        "series",
        "percent",
        "compare",
        "balance",
        "list_records",
    }
)
_UNRESOLVED_SUBJECT_INTENTS = frozenset({"sum", "extreme_item", "count", "avg", "list_records"})


def _out_of_scope_response(question: str) -> dict[str, Any]:
    similar = _similar_prompts(question)
    suggestions = list(dict.fromkeys([*similar, *intents.OFF_TOPIC_SUGGESTIONS]))[:4]
    return {
        "intent": "out_of_scope",
        "answer": intents.PURPOSE_ALERT_MESSAGE,
        "links": [
            {"label": "Abrir o Orçamento", "to": "/orcamento"},
            {"label": "Abrir a busca", "to": "/busca"},
        ],
        "suggestions": suggestions,
    }


def _navigate_response(corrected_question: str) -> dict[str, Any]:
    nav = specials.navigate(corrected_question)
    if nav:
        return nav
    return {
        "intent": "navigate",
        "answer": "Não encontrei essa tela exata. Aqui estão os atalhos mais usados:",
        "links": [
            {"label": "Orçamento", "to": "/orcamento"},
            {"label": "Cartões e faturas", "to": "/cartoes"},
            {"label": "Recorrências", "to": "/ajustes/recorrencias"},
            {"label": "Busca geral", "to": "/busca"},
        ],
        "suggestions": ["Onde encontro as metas?", "Como exporto meus dados?"],
    }


def _unknown_subject_response(index: UserEntityIndex, term: str) -> dict[str, Any]:
    close = _close_subjects(index, term)
    if close:
        return {
            "intent": "unknown_subject",
            "answer": f"Não achei categoria ou lançamento com “{term}”. Você quis dizer:",
            "suggestions": [f"Quanto gastei com {c.lower()}?" for c in close],
        }
    return {
        "intent": "unknown_subject",
        "answer": f"Não encontrei nenhuma categoria nem lançamento com “{term}”.",
        "links": [{"label": "Abrir a busca", "to": "/busca"}],
        "suggestions": SUGGESTIONS[:3],
    }


def _special_handlers(
    db: Session, user: User, plan: Any, index: UserEntityIndex, today: date
) -> dict[str, Any]:
    return {
        "cards": lambda: specials.cards_summary(db, user, plan, today),
        "invoices": lambda: specials.invoices_summary(db, user, plan, today),
        "due": lambda: specials.due_summary(db, user, plan, today),
        "can_spend": lambda: specials.can_spend_summary(db, user, today),
        "salary": lambda: specials.salary_summary(db, user, today),
        "logged": lambda: specials.logged_summary(db, user, plan, today),
        "installments": lambda: specials.installments_summary(db, user, plan, index, today),
        "loans": lambda: specials.loans_summary(db, user),
        "friend_loans": lambda: specials.friend_loans_summary(db, user, plan),
        "recurring": lambda: specials.recurring_summary(db, user, plan, index, today),
        "investments": lambda: specials.investments_summary(db, user),
        "accounts": lambda: specials.accounts_summary(db, user, plan),
        "transfers": lambda: specials.transfers_summary(db, user, plan, index),
        "projects": lambda: specials.projects_summary(db, user, plan, index),
        "goals": lambda: specials.goals_summary(db, user, today),
        "challenges": lambda: specials.challenges_summary(db, user),
        "planned": lambda: specials.planned_summary(db, user, today),
        "tax_deductible": lambda: specials.tax_deductible_summary(db, user, plan, index, today),
        "mei": lambda: specials.mei_summary(db, user, plan, today),
        "net_worth": lambda: specials.net_worth_summary(db, user),
        "review_pending": lambda: specials.review_pending_summary(db, user),
    }


def answer(
    db: Session,
    user: User,
    question: str,
    today: date | None = None,
    context: dict[str, Any] | None = None,
    debug: bool = False,
) -> dict[str, Any]:
    today = today or today_local()
    index = load_entity_index(db, user.id)
    plan, index = build_plan(db, user, question, today, context=context, entity_index=index)

    def finish(out: dict[str, Any], keep_ctx: bool = True) -> dict[str, Any]:
        out.setdefault("items", [])
        out.setdefault("links", [])
        out.setdefault("suggestions", [])
        out["context"] = _pack_context(plan) if keep_ctx else None
        if debug:
            out["debug"] = plan.to_debug_dict()
        return out

    if static := _SIMPLE_INTENTS.get(plan.intent):
        return finish(dict(static), keep_ctx=False)
    if plan.intent == "out_of_scope":
        return finish(_out_of_scope_response(plan.corrected_question), keep_ctx=False)
    if plan.intent == "entry_redirect":
        return finish(_entry_response(question, plan.domain), keep_ctx=False)
    if plan.intent == "locate_record":
        return finish(locator.locate_records(db, user, plan, index))
    if plan.intent == "navigate":
        return finish(_navigate_response(plan.corrected_question), keep_ctx=False)

    specials_map = _special_handlers(db, user, plan, index, today)
    if handler := specials_map.get(plan.intent):
        return finish(handler())

    # Assunto não resolvido sem outros filtros: avisa claramente em vez de somar tudo
    if plan.filters.unresolved_subject and plan.intent in _UNRESOLVED_SUBJECT_INTENTS:
        return finish(
            _unknown_subject_response(index, plan.filters.unresolved_subject), keep_ctx=False
        )

    if plan.intent in _ANALYTIC_INTENTS:
        return finish(executor.execute_analytic(db, user, plan, index, today))

    if plan.intent != "fallback":
        if nav := specials.navigate(plan.corrected_question):
            return finish(nav, keep_ctx=False)

    similar = _similar_prompts(plan.corrected_question)
    return finish(
        {
            "intent": "fallback",
            "answer": "Não tenho certeza do que você quer saber. Tente perguntar assim:",
            "links": [
                {"label": "Abrir o Orçamento", "to": "/orcamento"},
                {"label": "Abrir a busca", "to": "/busca"},
            ],
            "suggestions": list(dict.fromkeys([*similar, *SUGGESTIONS[:4]]))[:4],
        },
        keep_ctx=False,
    )
