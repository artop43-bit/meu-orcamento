"""Tire sua dúvida: fachada pública do motor composicional local (`app.services.bot`).

Tudo roda localmente no servidor, sem custo, sem serviço externo e sem IA: a pergunta
passa pelo planejador composicional (multi-filtro, agrupamentos, localizador universal
BM25/fuzzy, guarda de finalidade `out_of_scope` e navegação atualizada do Hub).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.models import User
from app.services.bot.engine.responder import SUGGESTIONS
from app.services.bot.engine.responder import answer as _answer

MAX_QUESTION = 300


def answer(
    db: Session,
    user: User,
    question: str,
    today: date | None = None,
    context: dict[str, Any] | None = None,
    debug: bool = False,
) -> dict[str, Any]:
    return _answer(db, user, question, today=today, context=context, debug=debug)


__all__ = ["MAX_QUESTION", "SUGGESTIONS", "answer"]
