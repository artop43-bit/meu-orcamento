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

# Categoria padrão → palavras (sem acento, minúsculas). Também casa com categorias
# criadas pelo usuário que tenham o mesmo nome.
KEYWORDS: dict[str, list[str]] = {
    "Moradia": [
        "aluguel",
        "condominio",
        "iptu",
        "luz",
        "energia",
        "enel",
        "cemig",
        "copel",
        "light",
        "agua",
        "sabesp",
        "saneamento",
        "gas",
        "comgas",
        "ultragaz",
        "reforma",
        "moveis",
        "financiamento imovel",
        "prestacao casa",
        "diarista",
        "faxina",
    ],
    "Alimentação": [
        "mercado",
        "supermercado",
        "feira",
        "padaria",
        "acougue",
        "hortifruti",
        "ifood",
        "restaurante",
        "lanche",
        "lanchonete",
        "pizza",
        "hamburguer",
        "almoco",
        "jantar",
        "cafe",
        "atacadao",
        "assai",
        "carrefour",
        "pao de acucar",
        "extra",
        "dia ",
        "rappi",
        "marmita",
        "sorvete",
        "doceria",
    ],
    "Transporte": [
        "uber",
        "99",
        "taxi",
        "onibus",
        "metro",
        "trem",
        "bilhete unico",
        "combustivel",
        "gasolina",
        "etanol",
        "alcool",
        "posto",
        "shell",
        "ipiranga",
        "estacionamento",
        "pedagio",
        "sem parar",
        "ipva",
        "licenciamento",
        "seguro carro",
        "mecanico",
        "oficina",
        "pneu",
        "revisao",
        "multa",
        "financiamento carro",
        "moto",
    ],
    "Saúde": [
        "farmacia",
        "drogaria",
        "remedio",
        "medicamento",
        "droga raia",
        "drogasil",
        "pague menos",
        "consulta",
        "medico",
        "dentista",
        "exame",
        "laboratorio",
        "plano de saude",
        "unimed",
        "amil",
        "hapvida",
        "bradesco saude",
        "sulamerica",
        "psicologo",
        "terapia",
        "academia",
        "smart fit",
        "fisioterapia",
        "otica",
        "oculos",
        "hospital",
    ],
    "Educação": [
        "escola",
        "faculdade",
        "mensalidade escolar",
        "curso",
        "udemy",
        "alura",
        "livro",
        "livraria",
        "material escolar",
        "apostila",
        "ingles",
        "idiomas",
        "matricula",
        "uniforme",
        "pos graduacao",
        "creche",
    ],
    "Serviços": [
        "internet",
        "telefone",
        "celular",
        "vivo",
        "claro",
        "tim",
        "oi ",
        "netflix",
        "spotify",
        "disney",
        "prime video",
        "amazon prime",
        "hbo",
        "max",
        "globoplay",
        "youtube premium",
        "icloud",
        "google one",
        "assinatura",
        "streaming",
        "banco",
        "tarifa",
        "anuidade",
        "seguro",
        "contador",
        "lavanderia",
        "cabeleireiro",
        "barbeiro",
        "manicure",
        "correios",
    ],
    "Lazer": [
        "cinema",
        "show",
        "teatro",
        "ingresso",
        "viagem",
        "hotel",
        "airbnb",
        "passagem",
        "bar",
        "balada",
        "festa",
        "presente",
        "aniversario",
        "jogo",
        "steam",
        "playstation",
        "xbox",
        "nintendo",
        "passeio",
        "parque",
        "praia",
        "clube",
        "cerveja",
        "churrasco",
    ],
}

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

    # 2. Palavras-chave.
    by_name = {normalize(c.name): c for c in categories.values()}
    padded = f" {text} "
    best: tuple[int, Category] | None = None
    for name, words in KEYWORDS.items():
        category = by_name.get(normalize(name))
        if category is None:
            continue
        for word in words:
            key = word.strip()
            if re.search(rf"(^|\W){re.escape(key)}(\W|$)", padded):
                # A palavra mais longa vence ("seguro carro" antes de "seguro").
                if best is None or len(key) > best[0]:
                    best = (len(key), category)
    if best is not None:
        return _out(best[1], "keywords")
    return None


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
