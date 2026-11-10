"""Histórico do Tire sua dúvida (v1.7.5).

As conversas ficam na conta de quem perguntou e são apagadas sozinhas 30 dias depois da última
mensagem (limpeza diária em app.cli e a cada acesso). Quem desliga a opção em Preferências tem
as conversas apagadas na hora e nada mais é guardado.
"""

import json
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.types import utcnow
from app.models import AskConversation, AskMessage, User

RETENTION = timedelta(days=30)
MAX_MESSAGES = 60  # por conversa; depois disso a pessoa começa outra


def purge(db: Session, user: User | None = None) -> int:
    """Apaga as conversas paradas há mais de 30 dias (de todos ou de um usuário)."""
    query = delete(AskConversation).where(AskConversation.updated_at <= utcnow() - RETENTION)
    if user is not None:
        query = query.where(AskConversation.user_id == user.id)
    ids = select(AskConversation.id).where(AskConversation.updated_at <= utcnow() - RETENTION)
    if user is not None:
        ids = ids.where(AskConversation.user_id == user.id)
    db.execute(delete(AskMessage).where(AskMessage.conversation_id.in_(ids)))
    return db.execute(query).rowcount


def _owned(db: Session, user: User, conversation_id: uuid.UUID) -> AskConversation:
    item = db.get(AskConversation, conversation_id)
    if item is None or item.user_id != user.id:
        raise AppError(404, "not_found", "Conversa não encontrada.")
    return item


def conversations(db: Session, user: User) -> list[AskConversation]:
    purge(db, user)
    db.commit()
    return list(
        db.scalars(
            select(AskConversation)
            .where(AskConversation.user_id == user.id)
            .order_by(AskConversation.updated_at.desc())
            .limit(100)
        )
    )


def messages(db: Session, user: User, conversation_id: uuid.UUID) -> list[dict[str, Any]]:
    item = _owned(db, user, conversation_id)
    rows = db.scalars(
        select(AskMessage)
        .where(AskMessage.conversation_id == item.id)
        .order_by(AskMessage.created_at)
    )
    return [
        {
            "id": r.id,
            "question": r.question,
            "answer": json.loads(r.answer),
            "created_at": r.created_at,
        }
        for r in rows
    ]


def last_context(db: Session, user: User, conversation_id: uuid.UUID) -> dict[str, Any] | None:
    item = _owned(db, user, conversation_id)
    last = db.scalar(
        select(AskMessage)
        .where(AskMessage.conversation_id == item.id)
        .order_by(AskMessage.created_at.desc())
        .limit(1)
    )
    if last is None:
        return None
    context = json.loads(last.answer).get("context")
    return context if isinstance(context, dict) else None


def record(
    db: Session,
    user: User,
    conversation_id: uuid.UUID | None,
    question: str,
    answer: dict[str, Any],
) -> uuid.UUID | None:
    """Guarda a pergunta e a resposta. Devolve o id da conversa (None se o histórico está
    desligado)."""
    if not user.ask_history:
        return None
    now = utcnow()
    item = _owned(db, user, conversation_id) if conversation_id else None
    if item is None:
        item = AskConversation(user_id=user.id, title=question[:200], created_at=now)
        db.add(item)
        db.flush()
    item.updated_at = now
    count = len(
        list(db.scalars(select(AskMessage.id).where(AskMessage.conversation_id == item.id)))
    )
    if count < MAX_MESSAGES:
        db.add(
            AskMessage(
                conversation_id=item.id,
                question=question[:200],
                answer=json.dumps(answer, ensure_ascii=False, default=str),
                created_at=now,
            )
        )
    db.commit()
    return item.id


def remove(db: Session, user: User, conversation_id: uuid.UUID | None = None) -> int:
    """Apaga uma conversa ou, sem id, todas."""
    ids = select(AskConversation.id).where(AskConversation.user_id == user.id)
    query = delete(AskConversation).where(AskConversation.user_id == user.id)
    if conversation_id is not None:
        _owned(db, user, conversation_id)
        ids = ids.where(AskConversation.id == conversation_id)
        query = query.where(AskConversation.id == conversation_id)
    db.execute(delete(AskMessage).where(AskMessage.conversation_id.in_(ids)))
    count = db.execute(query).rowcount
    db.commit()
    return count


def set_enabled(db: Session, user: User, enabled: bool) -> None:
    user.ask_history = enabled
    db.commit()
    if not enabled:
        remove(db, user)


def export(db: Session, user: User) -> list[dict[str, Any]]:
    out = []
    for item in conversations(db, user):
        out.append(
            {
                "title": item.title,
                "updated_at": item.updated_at.isoformat(),
                "messages": [
                    {"question": m["question"], "answer": m["answer"].get("answer")}
                    for m in messages(db, user, item.id)
                ],
            }
        )
    return out
