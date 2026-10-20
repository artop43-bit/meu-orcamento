"""Caixa de mensagens (v0.9): respostas às solicitações e recados da administração.

Cada mensagem fica na caixa do usuário (com "não lida") e, se ele não desligou, vai também por
e-mail. Recados marcados como importantes ficam fixados no topo e sempre geram e-mail.
"""

import uuid
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.types import utcnow
from app.models import Announcement, InboxItem, SupportThread, User
from app.services import notify, push
from app.services.auth import Mailer

PREVIEW = 600  # caracteres do texto no e-mail


def _excerpt(text: str) -> str:
    text = text.strip()
    return text if len(text) <= PREVIEW else text[: PREVIEW - 1].rstrip() + "…"


def _email(mail: Mailer, user: User, message: notify.Message) -> None:
    text, body_html, headers = notify.render(message, user)
    mail(user.email, message.subject, text, body_html, headers)


def _can_email(user: User, force: bool = False) -> bool:
    allowed = force or user.notify_messages
    return user.email_verified and user.access_status != "blocked" and allowed


# ---------------------------------------------------------------- resposta a uma solicitação


def notify_reply(db: Session, thread: SupportThread, body: str, mail: Mailer) -> InboxItem:
    """A administração respondeu: mensagem na caixa e, se o usuário quiser, e-mail."""
    user = db.get(User, thread.user_id)
    assert user is not None
    item = InboxItem(
        user_id=user.id,
        kind="reply",
        title=f"Resposta à sua solicitação: {thread.title}"[:160],
        body=body,
        thread_id=thread.id,
    )
    db.add(item)
    push.send(
        db,
        user,
        "messages",
        "Sua solicitação foi respondida",
        thread.title,
        f"/ajustes/solicitacoes/{thread.id}",
    )
    if _can_email(user):
        _email(
            mail,
            user,
            notify.Message(
                subject=f"Sua solicitação foi respondida: {thread.title}"[:200],
                heading="Sua solicitação foi respondida",
                intro=f"A administração respondeu à solicitação “{thread.title}”.",
                sections=[notify.Section(title="Resposta", note=_excerpt(body))],
                button=("Abrir a conversa", notify._link(f"/ajustes/solicitacoes/{thread.id}")),
                unsubscribe_kind="messages",
            ),
        )
    return item


# ---------------------------------------------------------------- caixa do usuário


def list_items(db: Session, user: User, limit: int = 200) -> list[InboxItem]:
    """Importantes não lidas primeiro; depois da mais recente para a mais antiga."""
    unread_important = (InboxItem.important.is_(True)) & (InboxItem.read_at.is_(None))
    return list(
        db.scalars(
            select(InboxItem)
            .where(InboxItem.user_id == user.id)
            .order_by(unread_important.desc(), InboxItem.created_at.desc(), InboxItem.id)
            .limit(limit)
        )
    )


def unread_count(db: Session, user: User) -> int:
    return (
        db.scalar(
            select(func.count()).where(InboxItem.user_id == user.id, InboxItem.read_at.is_(None))
        )
        or 0
    )


def mark_read(db: Session, user: User, item_id: uuid.UUID, read: bool = True) -> InboxItem:
    item = db.get(InboxItem, item_id)
    if item is None or item.user_id != user.id:
        raise AppError(404, "not_found", "Mensagem não encontrada.")
    item.read_at = (item.read_at or utcnow()) if read else None
    db.commit()
    return item


def mark_all_read(db: Session, user: User) -> int:
    result = db.execute(
        update(InboxItem)
        .where(InboxItem.user_id == user.id, InboxItem.read_at.is_(None))
        .values(read_at=utcnow())
    )
    db.commit()
    return result.rowcount or 0  # type: ignore[attr-defined]


def mark_thread_read(db: Session, user: User, thread_id: uuid.UUID) -> None:
    """Abrir a conversa conta como leitura das respostas dela na caixa."""
    db.execute(
        update(InboxItem)
        .where(
            InboxItem.user_id == user.id,
            InboxItem.thread_id == thread_id,
            InboxItem.read_at.is_(None),
        )
        .values(read_at=utcnow())
    )


# ---------------------------------------------------------------- recados da administração


def _audience(db: Session, include_pending: bool) -> list[User]:
    statuses = ["approved", "pending"] if include_pending else ["approved"]
    return list(
        db.scalars(select(User).where(User.access_status.in_(statuses)).order_by(User.created_at))
    )


def audience_count(db: Session, include_pending: bool) -> int:
    return len(_audience(db, include_pending))


def announce(
    db: Session,
    admin: User,
    title: str,
    body: str,
    important: bool,
    include_pending: bool,
    mail: Mailer,
) -> Announcement:
    people = _audience(db, include_pending)
    announcement = Announcement(
        author_id=admin.id,
        title=title,
        body=body,
        important=important,
        include_pending=include_pending,
        recipients=len(people),
    )
    db.add(announcement)
    db.flush()
    for user in people:
        db.add(
            InboxItem(
                user_id=user.id,
                kind="announcement",
                title=title,
                body=body,
                important=important,
                announcement_id=announcement.id,
            )
        )
        push.send(db, user, "messages", title, body, "/mensagens", force=important)
        if _can_email(user, force=important):
            _email(
                mail,
                user,
                notify.Message(
                    subject=f"{'Importante: ' if important else ''}{title}"[:200],
                    heading=title,
                    intro="Recado da administração do Meu Orçamento:",
                    sections=[notify.Section(title="Mensagem", note=_excerpt(body))],
                    button=("Abrir no app", notify._link("/mensagens")),
                    # Recados importantes não oferecem descadastro (são avisos do serviço).
                    unsubscribe_kind=None if important else "messages",
                ),
            )
    db.commit()
    return announcement


def list_announcements(db: Session) -> list[dict[str, Any]]:
    read = (
        select(func.count())
        .where(InboxItem.announcement_id == Announcement.id, InboxItem.read_at.is_not(None))
        .correlate(Announcement)
        .scalar_subquery()
    )
    rows = db.execute(select(Announcement, read).order_by(Announcement.created_at.desc()))
    return [{"announcement": a, "read": n} for a, n in rows]
