"""Sugestão de categoria pela descrição e autocompletar de lançamentos.

Primeiro aprende com o histórico do próprio usuário (o que ele já lançou com a mesma
descrição); se não houver, usa um dicionário de palavras-chave comuns no Brasil.
"""

import re
import unicodedata
import uuid
from collections import Counter
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.months import add_months
from app.models import Category, Expense, User
from app.services.category_words import EXACT_ONLY, FALLBACK, WORDS

HISTORY_MONTHS = 18


def normalize(text: str) -> str:
    """Minúsculas, sem acento e sem números de parcela ("TV 2/10" → "tv")."""
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\b\d+\s*/\s*\d+\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _recent_expenses(db: Session, user: User, today: date) -> list[Expense]:
    since = add_months(today.replace(day=1), -HISTORY_MONTHS)
    return list(
        db.scalars(
            select(Expense)
            .where(Expense.user_id == user.id, Expense.month >= since)
            .order_by(Expense.created_at.desc())
            .limit(2000)
        )
    )


def suggest_category(
    db: Session, user: User, description: str, today: date | None = None
) -> dict[str, Any] | None:
    text = normalize(description)
    if len(text) < 2:
        return None
    categories = {c.id: c for c in db.scalars(select(Category).where(Category.user_id == user.id))}

    # 0. Regra criada pelo usuário.
    from app.services import rules

    ruled = rules.matcher(db, user)(description)
    if ruled is not None and ruled in categories:
        return _out(categories[ruled], "rule")

    # 1. Histórico: o que você já usou para essa descrição (ou que começa igual).
    votes: Counter[uuid.UUID] = Counter()
    for expense in _recent_expenses(db, user, today or date.today()):
        if expense.category_id is None or expense.category_id not in categories:
            continue
        past = normalize(expense.description)
        if past == text:
            votes[expense.category_id] += 3
        elif len(text) >= 4 and (past.startswith(text) or text.startswith(past)):
            votes[expense.category_id] += 1
    if votes:
        category_id, _ = votes.most_common(1)[0]
        return _out(categories[category_id], "history")

    # 2. Dicionário de termos comuns.
    name = keyword_category(description)
    if name is not None:
        by_name = {normalize(c.name): c for c in categories.values()}
        for candidate in (name, FALLBACK.get(name)):
            if candidate and normalize(candidate) in by_name:
                return _out(by_name[normalize(candidate)], "keywords")
    return None


def tokens(text: str) -> list[str]:
    """Palavras da descrição, já sem acento e sem códigos de extrato ("IFD*IFOOD" → ifd, ifood)."""
    return [t for t in re.split(r"[^a-z0-9&]+", normalize(text)) if t]


def keyword_category(description: str) -> str | None:
    """Nome da categoria padrão sugerida pelo dicionário, ou None."""
    words = tokens(description)
    if not words:
        return None
    phrase = f" {' '.join(words)} "
    best: tuple[int, str] | None = None
    for term, category in WORDS.items():
        if " " in term or "&" in term:
            if f" {term} " not in phrase:
                continue
            score = len(term) * 10
        elif term in words:
            score = len(term) * 10
        elif (
            len(term) >= 4
            and term not in EXACT_ONLY
            and any(w.startswith(term) and len(w) - len(term) <= 4 for w in words)
        ):
            # Variações: plural e sufixos ("pizza" → "pizzaria", "farmac" → "farmacias").
            score = len(term)
        else:
            continue
        if best is None or score > best[0]:
            best = (score, category)
    return best[1] if best else None


def _out(category: Category, source: str) -> dict[str, Any]:
    return {"category_id": category.id, "name": category.name, "source": source}


def describe_suggestions(
    db: Session, user: User, query: str, limit: int = 8, today: date | None = None
) -> list[dict[str, Any]]:
    """Descrições já usadas que combinam com o texto, com o último valor e categoria."""
    text = normalize(query)
    if not text:
        return []
    found: dict[str, dict[str, Any]] = {}
    for expense in _recent_expenses(db, user, today or date.today()):
        if expense.installment_group_id is not None:
            continue
        key = normalize(expense.description)
        if text not in key:
            continue
        entry = found.get(key)
        if entry is None:
            found[key] = {
                "description": expense.description,
                "amount": expense.amount,
                "category_id": expense.category_id,
                "payment_method": expense.payment_method,
                "count": 1,
                "starts": key.startswith(text),
            }
        else:
            entry["count"] += 1
    ranked = sorted(found.values(), key=lambda e: (not e["starts"], -e["count"]))
    return [{k: v for k, v in e.items() if k != "starts"} for e in ranked[:limit]]
