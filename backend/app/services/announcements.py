"""Recados com respostas em thread (v1.3.1).

A thread é pública: todos que receberam o recado veem as respostas, com o nome do perfil
(nunca o e-mail). A pessoa pode apagar a própria resposta; a administração apaga qualquer uma.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import Announcement, AnnouncementReply, InboxItem, User
from app.services import files

MAX_REPLY = 1000


def _is_admin(user: User) -> bool:
    from app.services.auth import is_admin

    return is_admin(user)


def _visible(db: Session, user: User, announcement: Announcement) -> bool:
    """Quem recebeu o recado (está na caixa da pessoa) ou a administração."""
    if _is_admin(user):
        return True
    return (
        db.scalar(
            select(InboxItem.id).where(
                InboxItem.user_id == user.id, InboxItem.announcement_id == announcement.id
            )
        )
        is not None
    )


def _get(db: Session, user: User, announcement_id: uuid.UUID) -> Announcement:
    announcement = db.get(Announcement, announcement_id)
    if announcement is None or not _visible(db, user, announcement):
        raise AppError(404, "not_found", "Recado não encontrado.")
    return announcement


def _name(author: User | None, from_admin: bool) -> str:
    if author is None:
        return "Conta excluída"
    if author.display_name:
        return author.display_name
    return "Administração" if from_admin else "Participante"


def threads(db: Session, user: User, ids: list[uuid.UUID]) -> dict[uuid.UUID, list[dict[str, Any]]]:
    """Respostas de vários recados de uma vez, em ordem de envio."""
    if not ids:
        return {}
    rows = list(
        db.execute(
            select(AnnouncementReply, User)
            .join(User, User.id == AnnouncementReply.author_id, isouter=True)
            .where(AnnouncementReply.announcement_id.in_(ids))
            .order_by(AnnouncementReply.created_at)
        )
    )
    avatars = files.latest_ids(db, list({u.id for _, u in rows if u is not None}), "avatar")
    admin = _is_admin(user)
    result: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for reply, author in rows:
        result.setdefault(reply.announcement_id, []).append(
            {
                "id": reply.id,
                "author_name": _name(author, reply.from_admin),
                "avatar_id": avatars.get(author.id) if author else None,
                "from_admin": reply.from_admin,
                "mine": reply.author_id == user.id,
                "migrated": reply.migrated,
                "can_delete": admin or reply.author_id == user.id,
                "body": reply.body,
                "created_at": reply.created_at,
            }
        )
    return result


def feed(db: Session, user: User) -> list[dict[str, Any]]:
    """Recados da pessoa (todos, para a administração), do mais novo ao mais antigo."""
    if _is_admin(user):
        stmt = select(Announcement)
    else:
        stmt = select(Announcement).join(
            InboxItem,
            (InboxItem.announcement_id == Announcement.id) & (InboxItem.user_id == user.id),
        )
    announcements = list(db.scalars(stmt.order_by(Announcement.created_at.desc()).limit(100)))
    replies = threads(db, user, [a.id for a in announcements])
    return [{"announcement": a, "replies": replies.get(a.id, [])} for a in announcements]


def reply(db: Session, user: User, announcement_id: uuid.UUID, body: str) -> dict[str, Any]:
    announcement = _get(db, user, announcement_id)
    text = body.strip()
    if not text:
        raise AppError(400, "empty_message", "Escreva a resposta.")
    if len(text) > MAX_REPLY:
        raise AppError(400, "too_long", f"A resposta pode ter até {MAX_REPLY} caracteres.")
    db.add(
        AnnouncementReply(
            announcement_id=announcement.id,
            author_id=user.id,
            from_admin=_is_admin(user),
            body=text,
        )
    )
    db.commit()
    return {
        "announcement": announcement,
        "replies": threads(db, user, [announcement.id]).get(announcement.id, []),
    }


def delete_reply(db: Session, user: User, reply_id: uuid.UUID) -> None:
    item = db.get(AnnouncementReply, reply_id)
    if item is None or not (item.author_id == user.id or _is_admin(user)):
        raise AppError(404, "not_found", "Resposta não encontrada.")
    announcement = db.get(Announcement, item.announcement_id)
    if announcement is None or not _visible(db, user, announcement):
        raise AppError(404, "not_found", "Resposta não encontrada.")
    db.delete(item)
    db.commit()
