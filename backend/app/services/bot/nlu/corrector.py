"""Correção ortográfica protegida e detecção de tentativa de lançamento."""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Category,
    CreditCard,
    Expense,
    Goal,
    Income,
    Investment,
    Loan,
    MoneyAccount,
    OtherDebt,
    PersonalLoan,
    PlannedExpense,
    Project,
    RecurringItem,
    SplitShare,
)
from app.services.bot.lexicon import core, domain, intents, navigation
from app.services.bot.text_utils import normalize, within_one


def _alt(terms: list[str]) -> str:
    ordered = sorted({t for t in terms if t}, key=len, reverse=True)
    return "|".join(re.escape(t).replace(r"\ ", r"\s+") for t in ordered)


def _build_vocabulary() -> tuple[set[str], dict[tuple[str, int], list[str]]]:
    known: set[str] = (
        set(core.COMMON_STOPWORDS)
        | set(core.ABBREVIATIONS)
        | {
            "ganhou",
            "ganhar",
            "ganharam",
            "jogo",
            "jogos",
            "carro",
            "carros",
            "torre",
            "eiffel",
            "praca",
            "guitarra",
            "tocar",
            "rapido",
            "rapida",
            "nome",
            "nomes",
            "planeta",
            "melhor",
            "maior",
            "menor",
            "segundo",
        }
    )
    targets: set[str] = set()

    word_sources = [
        *core.INCOME_VERBS,
        *core.INCOME_NOUNS,
        *core.ENTRY_VERBS,
        *core.ENTRY_COMMANDS,
        *core.ENTRY_SOFT_VERBS,
        *core.ENTRY_NOUNS,
        *core.QUESTION_STARTERS,
        *core.ASK_VERBS,
        *core.ANALYTIC_WORDS,
        *core.PAYMENT_TERMS,
        *core.WEEKDAYS,
        *core.DATE_WORDS,
        *(term for terms in domain.ENTITY_TERMS.values() for term in terms),
        *(term for terms in domain.STATUS_TRIGGERS.values() for term in terms),
        *(term for terms in domain.DEDUCTIBLE_TERMS.values() for term in terms),
        *domain.MONTH_NAMES_NORM,
        *intents.LOCATE_RECORD_TRIGGERS,
        *intents.NAVIGATE_HINT_WORDS,
        *intents.MOST_TRIGGERS,
        *intents.LEAST_TRIGGERS,
        *intents.PERCENT_TRIGGERS,
        *intents.COUNT_TRIGGERS,
        *intents.AVERAGE_TRIGGERS,
        *intents.PER_DAY_TRIGGERS,
        *intents.PER_WEEK_TRIGGERS,
        *intents.COMPARE_TRIGGERS,
        *intents.SERIES_TRIGGERS,
        *intents.LIST_RECORDS_TRIGGERS,
        *(term for terms in intents.GROUPING_TRIGGERS.values() for term in terms),
        *intents.ALL_TIME_TRIGGERS,
    ]
    for phrase in word_sources:
        for tok in phrase.split():
            if tok.isalpha():
                known.add(tok)
                if len(tok) >= 6:
                    targets.add(tok)

    for _, _, keys in navigation.PLACES:
        for tok in keys.split():
            if tok.isalpha():
                known.add(tok)
                if len(tok) >= 6:
                    targets.add(tok)

    for term in core.WORDS:
        if " " in term or "&" in term:
            for tok in term.split():
                if tok.isalpha():
                    known.add(tok)
            continue
        known.add(term)
        if len(term) >= 7 and term.isalpha():
            targets.add(term)

    buckets: dict[tuple[str, int], list[str]] = defaultdict(list)
    for word in targets:
        buckets[(word[0], len(word))].append(word)
    return known, buckets


_KNOWN, _BUCKETS = _build_vocabulary()


def user_own_words(db: Session, user_id: uuid.UUID) -> set[str]:
    """Todas as palavras reais cadastradas pelo usuário: nunca são alteradas pelo corretor."""
    words: set[str] = set()
    queries = [
        select(Category.name).where(Category.user_id == user_id),
        select(CreditCard.name).where(CreditCard.user_id == user_id),
        select(MoneyAccount.name).where(MoneyAccount.user_id == user_id),
        select(Project.name).where(Project.user_id == user_id),
        select(Goal.name).where(Goal.user_id == user_id),
        select(Investment.name).where(Investment.user_id == user_id),
        select(Loan.name).where(Loan.user_id == user_id),
        select(OtherDebt.name).where(OtherDebt.user_id == user_id),
        select(PersonalLoan.person).where(PersonalLoan.user_id == user_id),
        select(SplitShare.person).where(SplitShare.user_id == user_id),
        select(RecurringItem.description).where(RecurringItem.user_id == user_id),
        select(PlannedExpense.description).where(PlannedExpense.user_id == user_id),
        select(Expense.description).where(Expense.user_id == user_id).distinct().limit(4000),
        select(Income.description).where(Income.user_id == user_id).distinct().limit(1000),
    ]
    for query in queries:
        for text in db.scalars(query):
            if text:
                words.update(normalize(text).split())
    return words


def fix_typos(text: str, protected: Callable[[], set[str]] | None = None) -> str:
    """Resolve abreviações comuns e corrige erros de 1 letra protegendo termos do usuário."""
    words = text.split()
    own: set[str] | None = None
    out: list[str] = []
    for word in words:
        if word in core.ABBREVIATIONS:
            out.append(core.ABBREVIATIONS[word])
            continue
        if len(word) < 6 or not word.isalpha() or word in _KNOWN:
            out.append(word)
            continue
        found = [
            candidate
            for size in (len(word) - 1, len(word), len(word) + 1)
            for candidate in _BUCKETS.get((word[0], size), ())
            if within_one(word, candidate)
        ]
        if len(found) != 1:
            out.append(word)
            continue
        if protected is not None:
            if own is None:
                own = protected()
            if word in own:
                out.append(word)
                continue
        out.append(found[0])
    return " ".join(out)


# ---------------------------------------------------------------- detecção de lançamento
_STARTERS = re.compile(rf"^(?:{_alt(core.QUESTION_STARTERS)})\b")
_ASK = re.compile(rf"^(?:{_alt(core.ASK_VERBS)})\b")
_ANALYTIC = re.compile(rf"\b(?:{_alt([*core.ANALYTIC_WORDS, 'top', 'ranking'])})\b")
_QUERY_WORDS = re.compile(
    r"\b(?:meus?|minhas?|todos|todas|lista|resumo|relatorio|extrato|aquele|aquela)\b"
)
_LOCATE = re.compile(rf"\b(?:{_alt(intents.LOCATE_RECORD_TRIGGERS)})\b")
_POLITE = re.compile(
    r"^(?:por favor|favor|quero|queria|preciso|vou|pode|poderia|bora|vamos|gostaria de)\s+"
)
_COMMAND = re.compile(rf"^(?:{_alt(core.ENTRY_COMMANDS)})\b")
_STRONG = re.compile(rf"^(?:{_alt([*core.ENTRY_VERBS, *core.INCOME_VERBS])})\b")
_SOFT = re.compile(rf"^(?:{_alt(core.ENTRY_SOFT_VERBS)})\b")
_ENTRY_THING = re.compile(
    r"\b(?:despesa|despesas|gasto|gastos|receita|receitas|renda|compra|compras|lancamento|lancamentos|"
    r"pagamento|entrada|saida|conta)\b"
)
_NEW_THING = re.compile(
    r"^(?:nova|novo)\s+(?:despesa|receita|renda|compra|conta|lancamento|gasto)\b"
)
_NOT_AMOUNT = re.compile(
    r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b|\bdia\s+\d{1,2}\b|\b\d{1,3}\s*x\b|"
    r"\b(?:em|de|desde|ate|ano)\s+20\d\d\b|\b20\d\d\b|"
    r"\b(?:ultim[oa]s?|proxim[oa]s?)\s+\d+\b|\b\d+\s*(?:dias?|meses|mes|semanas?|anos?|vezes|parcelas?|horas?)\b|"
    r"\b\d+\s*[oa]\b"
)
_AMOUNT = re.compile(r"(?<![\w/])(?:r\$\s*)?(\d+(?:[.,]\d+)*)(?:\s*(?:k|mil))?(?![\w/])")
_BEFORE_SUBJECT = {
    "com",
    "no",
    "na",
    "nos",
    "nas",
    "em",
    "de",
    "do",
    "da",
    "pro",
    "pra",
    "para",
    "ao",
}


def entry_guess(raw: str) -> str | None:
    """Identifica se a frase é uma tentativa de lançamento ('gastei 50 no mercado')."""
    if "?" in raw:
        return None
    text = re.sub(r"[!;:]+", " ", raw)
    text = re.sub(r"\s+", " ", text).strip().rstrip(".")
    if not text or re.match(r"e\b", text):
        return None
    if _LOCATE.search(text) or _ANALYTIC.search(text):
        return None
    plus = text.startswith("+")
    text = text.lstrip("+ ").strip()
    body = _POLITE.sub("", text)
    if _STARTERS.match(body) or _STARTERS.match(text):
        return None
    masked = _NOT_AMOUNT.sub(" ", body)
    amounts = list(_AMOUNT.finditer(masked))
    real = []
    for match in amounts:
        before = masked[: match.start()].split()
        if before and before[-1] in _BEFORE_SUBJECT and match.end() >= len(masked.rstrip()):
            continue
        real.append(match)
    has_amount = bool(real)
    command = _COMMAND.match(body) is not None
    if command and (has_amount or _ENTRY_THING.search(body)):
        return "amount" if has_amount else "command"
    if _NEW_THING.match(body):
        return "amount" if has_amount else "command"
    if not has_amount:
        return None
    if plus or _STRONG.match(body):
        return "amount"
    if _ASK.match(body) or _QUERY_WORDS.search(body):
        return None
    if _SOFT.match(body):
        return "amount"
    words = body.split()
    described = any(w.isalpha() and len(w) >= 2 for w in words)
    return "amount" if described and len(words) <= 8 else None
