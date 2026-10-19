"""Sugestões e problemas enviados de dentro do app (lidas por quem está em ADMIN_EMAILS)."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import Feedback, User


def is_admin(user: User) -> bool:
    return user.email.lower() in get_settings().admin_email_list()


def create(db: Session, user: User, data: dict[str, Any], user_agent: str | None) -> Feedback:
    item = Feedback(user_id=user.id, user_agent=(user_agent or "")[:300] or None, **data)
    db.add(item)
    db.commit()
    return item


def list_all(db: Session, user: User, limit: int = 200) -> list[tuple[Feedback, str | None]]:
    if not is_admin(user):
        raise AppError(403, "forbidden", "Só a administração vê as sugestões.")
    rows = db.execute(
        select(Feedback, User.email)
        .join(User, User.id == Feedback.user_id, isouter=True)
        .order_by(Feedback.created_at.desc())
        .limit(limit)
    )
    return [(f, email) for f, email in rows]


def set_status(db: Session, user: User, item_id: uuid.UUID, status: str) -> Feedback:
    if not is_admin(user):
        raise AppError(403, "forbidden", "Só a administração vê as sugestões.")
    item = db.get(Feedback, item_id)
    if item is None:
        raise AppError(404, "not_found", "Item não encontrado.")
    item.status = status
    db.commit()
    return item
