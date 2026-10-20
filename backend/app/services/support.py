"""Solicitações: cada uma é uma conversa entre o usuário e a administração.

Status: "open" (aguardando a administração), "in_progress" (em andamento), "planned"
(planejada para uma versão), "answered" (a administração respondeu), "resolved" (resolvida) e
"declined" (recusada). Uma nova mensagem do usuário reabre. Cada lado tem o seu "não lido".
Desde a v1.1 cada solicitação tem um número fixo (#1, #2...) para ser tratada como tarefa.
"""

import uuid
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.types import utcnow
from app.models import StoredFile, SupportMessage, SupportThread, User
from app.services import files
from app.services.auth import Mailer

MAX_FILES = 3
STATUSES = ("open", "in_progress", "planned", "answered", "resolved", "declined")
STATUS_LABELS = {
    "open": "Aberta",
    "in_progress": "Em andamento",
    "planned": "Planejada",
    "answered": "Respondida",
    "resolved": "Resolvida",
    "declined": "Recusada",
}


def _check_admin(user: User) -> None:
    from app.services.auth import is_admin

    if not is_admin(user):
        raise AppError(403, "forbidden", "Acesso restrito à administração.")


def _add_message(
    db: Session,
    thread: SupportThread,
    author: User,
    body: str,
    uploads: list[bytes],
    from_admin: bool,
) -> SupportMessage:
    if len(uploads) > MAX_FILES:
        raise AppError(400, "too_many_files", f"Envie no máximo {MAX_FILES} imagens por mensagem.")
    message = SupportMessage(
        thread_id=thread.id, author_id=author.id, from_admin=from_admin, body=body
    )
    db.add(message)
    db.flush()
    for raw in uploads:
        files.store(db, author, raw, "attachment", message_id=message.id)
    thread.last_message_at = message.created_at or utcnow()
    return message


def _next_number(db: Session) -> int:
    return (db.scalar(select(func.max(SupportThread.number))) or 0) + 1


def create_thread(
    db: Session,
    user: User,
    data: dict[str, Any],
    uploads: list[bytes],
    user_agent: str | None,
    announcement_id: uuid.UUID | None = None,
) -> SupportThread:
    thread = SupportThread(
        number=_next_number(db),
        announcement_id=announcement_id,
        user_id=user.id,
        title=data["title"],
        kind=data["kind"],
        status="open",
        user_unread=False,
        admin_unread=True,
        page=data.get("page"),
        app_version=data.get("app_version"),
        user_agent=(user_agent or "")[:300] or None,
    )
    db.add(thread)
    db.flush()
    _add_message(db, thread, user, data["message"], uploads, from_admin=False)
    db.commit()
    return thread


def _owned_thread(db: Session, user: User, thread_id: uuid.UUID) -> SupportThread:
    thread = db.get(SupportThread, thread_id)
    if thread is None or thread.user_id != user.id:
        raise AppError(404, "not_found", "Solicitação não encontrada.")
    return thread


def _any_thread(db: Session, thread_id: uuid.UUID) -> SupportThread:
    thread = db.get(SupportThread, thread_id)
    if thread is None:
        raise AppError(404, "not_found", "Solicitação não encontrada.")
    return thread


def list_mine(db: Session, user: User) -> list[SupportThread]:
    return list(
        db.scalars(
            select(SupportThread)
            .where(SupportThread.user_id == user.id)
            .order_by(SupportThread.last_message_at.desc())
        )
    )


def unread_count(db: Session, user: User) -> int:
    return (
        db.scalar(
            select(func.count()).where(
                SupportThread.user_id == user.id, SupportThread.user_unread.is_(True)
            )
        )
        or 0
    )


def messages(db: Session, thread: SupportThread) -> list[dict[str, Any]]:
    rows = list(
        db.scalars(
            select(SupportMessage)
            .where(SupportMessage.thread_id == thread.id)
            .order_by(SupportMessage.created_at, SupportMessage.id)
        )
    )
    attachments: dict[uuid.UUID, list[StoredFile]] = {}
    if rows:
        for item in db.scalars(
            select(StoredFile)
            .where(StoredFile.message_id.in_([m.id for m in rows]))
            .order_by(StoredFile.created_at)
        ):
            attachments.setdefault(item.message_id, []).append(item)  # type: ignore[arg-type]
    return [
        {
            "id": m.id,
            "from_admin": m.from_admin,
            "body": m.body,
            "created_at": m.created_at,
            "attachments": [
                {"id": f.id, "width": f.width, "height": f.height, "content_type": f.content_type}
                for f in attachments.get(m.id, [])
            ],
        }
        for m in rows
    ]


def open_mine(db: Session, user: User, thread_id: uuid.UUID) -> SupportThread:
    """Abre a conversa do próprio usuário e marca as respostas como lidas."""
    from app.services import inbox

    thread = _owned_thread(db, user, thread_id)
    thread.user_unread = False
    inbox.mark_thread_read(db, user, thread.id)
    db.commit()
    return thread


def reply_mine(
    db: Session, user: User, thread_id: uuid.UUID, body: str, uploads: list[bytes]
) -> SupportThread:
    thread = _owned_thread(db, user, thread_id)
    _add_message(db, thread, user, body, uploads, from_admin=False)
    # Nova mensagem do usuário: volta para a fila da administração (e reabre se estava resolvida).
    thread.status = "open"
    thread.admin_unread = True
    thread.user_unread = False
    db.commit()
    return thread


def resolve_mine(db: Session, user: User, thread_id: uuid.UUID) -> SupportThread:
    thread = _owned_thread(db, user, thread_id)
    thread.status = "resolved"
    db.commit()
    return thread


# ---------------------------------------------------------------- administração


def admin_open(db: Session, admin: User, thread_id: uuid.UUID) -> SupportThread:
    _check_admin(admin)
    thread = _any_thread(db, thread_id)
    if thread.admin_unread:
        thread.admin_unread = False
        db.commit()
    return thread


def admin_reply(
    db: Session,
    admin: User,
    thread_id: uuid.UUID,
    body: str,
    uploads: list[bytes],
    mail: Mailer | None = None,
) -> SupportThread:
    from app.services import inbox

    _check_admin(admin)
    thread = _any_thread(db, thread_id)
    _add_message(db, thread, admin, body, uploads, from_admin=True)
    thread.status = "answered"
    thread.user_unread = True
    thread.admin_unread = False
    if mail is not None:
        inbox.notify_reply(db, thread, body, mail)
    db.commit()
    return thread


def admin_set_status(
    db: Session,
    admin: User,
    thread_id: uuid.UUID,
    status: str,
    note: str | None = None,
    version: str | None = None,
    mail: Mailer | None = None,
) -> SupportThread:
    """Muda o status da tarefa (com nota e versão opcionais) e avisa a pessoa na caixa."""
    from app.services import inbox

    _check_admin(admin)
    if status not in STATUSES:
        raise AppError(400, "invalid_status", "Status inválido.")
    thread = _any_thread(db, thread_id)
    changed = thread.status != status or (note or None) != thread.status_note
    thread.status = status
    thread.status_note = (note or "").strip()[:200] or None
    thread.planned_version = (version or "").strip()[:20] or None
    if changed and mail is not None:
        inbox.notify_status(db, thread, mail)
    db.commit()
    return thread


def reply_announcement(
    db: Session, user: User, item_id: uuid.UUID, body: str, uploads: list[bytes]
) -> SupportThread:
    """Responder um recado: abre (ou continua) uma conversa ligada a ele."""
    from app.models import Announcement, InboxItem

    item = db.get(InboxItem, item_id)
    if item is None or item.user_id != user.id or item.announcement_id is None:
        raise AppError(404, "not_found", "Recado não encontrado.")
    announcement = db.get(Announcement, item.announcement_id)
    if announcement is None:
        raise AppError(404, "not_found", "Recado não encontrado.")
    thread = db.scalar(
        select(SupportThread).where(
            SupportThread.user_id == user.id, SupportThread.announcement_id == announcement.id
        )
    )
    if thread is None:
        return create_thread(
            db,
            user,
            {
                "title": f"Resposta ao recado: {announcement.title}"[:120],
                "kind": "other",
                "message": body,
            },
            uploads,
            None,
            announcement_id=announcement.id,
        )
    return reply_mine(db, user, thread.id, body, uploads)


def _search(stmt: Select[Any], query: str | None) -> Select[Any]:
    if not query:
        return stmt
    text = query.strip()
    # "#12" ou "12": busca pelo número da solicitação.
    if text.lstrip("#").isdigit():
        return stmt.where(SupportThread.number == int(text.lstrip("#")))
    like = f"%{text.lower()}%"
    in_messages = (
        select(SupportMessage.thread_id)
        .where(func.lower(SupportMessage.body).like(like))
        .scalar_subquery()
    )
    return stmt.where(
        or_(
            func.lower(SupportThread.title).like(like),
            func.lower(User.email).like(like),
            func.lower(func.coalesce(User.display_name, "")).like(like),
            SupportThread.id.in_(in_messages),
        )
    )


def admin_list(
    db: Session,
    admin: User,
    query: str | None = None,
    status: str | None = None,
    user_id: uuid.UUID | None = None,
    limit: int = 300,
    kind: str | None = None,
    version: str | None = None,
) -> list[tuple[SupportThread, User, int]]:
    """Solicitações com o autor e o número de mensagens, da última mensagem para a primeira."""
    _check_admin(admin)
    count = (
        select(func.count())
        .where(SupportMessage.thread_id == SupportThread.id)
        .correlate(SupportThread)
        .scalar_subquery()
    )
    stmt = select(SupportThread, User, count).join(User, User.id == SupportThread.user_id)
    if status:
        stmt = stmt.where(SupportThread.status == status)
    if user_id:
        stmt = stmt.where(SupportThread.user_id == user_id)
    if kind:
        stmt = stmt.where(SupportThread.kind == kind)
    if version:
        stmt = stmt.where(SupportThread.planned_version == version)
    stmt = _search(stmt, query)
    stmt = stmt.order_by(SupportThread.last_message_at.desc()).limit(limit)
    return [(t, u, n) for t, u, n in db.execute(stmt)]


def admin_by_user(db: Session, admin: User, query: str | None = None) -> list[dict[str, Any]]:
    """Uma linha por pessoa: total de solicitações, em aberto, não lidas e a mais recente."""
    rows = admin_list(db, admin, query=query, limit=5000)
    people: dict[uuid.UUID, dict[str, Any]] = {}
    for thread, user, _ in rows:
        item = people.setdefault(
            user.id,
            {"user": user, "total": 0, "open": 0, "unread": 0, "last_message_at": None},
        )
        item["total"] += 1
        item["open"] += thread.status == "open"
        item["unread"] += thread.admin_unread
        if item["last_message_at"] is None or thread.last_message_at > item["last_message_at"]:
            item["last_message_at"] = thread.last_message_at
    return sorted(people.values(), key=lambda p: p["last_message_at"], reverse=True)


def admin_versions(db: Session, admin: User) -> list[str]:
    _check_admin(admin)
    rows = db.scalars(
        select(SupportThread.planned_version)
        .where(SupportThread.planned_version.is_not(None))
        .distinct()
    )
    return sorted({v for v in rows if v}, reverse=True)


def admin_counts(db: Session, admin: User) -> dict[str, int]:
    _check_admin(admin)
    counts = {s: 0 for s in STATUSES}
    owned = select(SupportThread).join(User, User.id == SupportThread.user_id).subquery()
    for status, total in db.execute(select(owned.c.status, func.count()).group_by(owned.c.status)):
        counts[status] = total
    counts["unread"] = (
        db.scalar(select(func.count()).select_from(owned).where(owned.c.admin_unread.is_(True)))
        or 0
    )
    return counts
