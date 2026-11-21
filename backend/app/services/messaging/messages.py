"""Mensagens das conversas: lista com sincronização por data de alteração e envio pela fila."""

import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.types import utcnow
from app.models import MessagingMedia, MessagingMessage, User
from app.services import admin as admin_service
from app.services.messaging import connector_client
from app.services.messaging.chats import get_chat
from app.services.messaging.media import media_label, store_media
from app.services.messaging.sessions import get_or_create_session

MESSAGE_TYPES = {"chat", "image", "audio", "video", "document", "sticker", "other"}
MESSAGE_STATUSES = ("pending", "sent", "delivered", "read", "failed")
PREVIEW_LIMIT = 180
# Sobreposição de segurança do "since": relógios e gravações quase simultâneas.
SINCE_OVERLAP = timedelta(seconds=5)


def preview(text: str) -> str:
    compact = re.sub(r"\s+", " ", text or "").strip()
    if len(compact) <= PREVIEW_LIMIT:
        return compact
    return compact[: PREVIEW_LIMIT - 1].rstrip() + "…"


def serialize_message(
    msg: MessagingMessage,
    reply_msg: MessagingMessage | None = None,
    media_meta: tuple[uuid.UUID, str, str | None, int] | None = None,
) -> dict[str, Any]:
    media_id = media_meta[0] if media_meta is not None else msg.media_id
    return {
        "id": msg.id,
        "chat_id": msg.chat_id,
        "direction": msg.direction,
        "body": msg.body,
        "message_type": msg.message_type,
        "status": msg.status,
        "external_id": msg.external_id,
        "reply_to_id": msg.reply_to_id,
        "reply_preview": preview(reply_msg.body) if reply_msg is not None else None,
        "media_id": media_id,
        "media_mime": media_meta[1] if media_meta is not None else None,
        "media_name": media_meta[2] if media_meta is not None else None,
        "media_size": media_meta[3] if media_meta is not None else None,
        "media_url": f"/api/messaging/media/{media_id}" if media_id is not None else None,
        "error_detail": msg.error_detail,
        "sent_at": msg.sent_at,
        "created_at": msg.created_at,
        "updated_at": msg.updated_at,
    }


def _serialize_with_replies(
    db: Session, user: User, rows: list[MessagingMessage]
) -> list[dict[str, Any]]:
    reply_ids = {m.reply_to_id for m in rows if m.reply_to_id is not None}
    replies: dict[uuid.UUID, MessagingMessage] = {}
    if reply_ids:
        for ref in db.scalars(
            select(MessagingMessage).where(
                MessagingMessage.id.in_(reply_ids),
                MessagingMessage.user_id == user.id,
            )
        ).all():
            replies[ref.id] = ref
    media_ids = {m.media_id for m in rows if m.media_id is not None}
    media_map: dict[uuid.UUID, tuple[uuid.UUID, str, str | None, int]] = {}
    if media_ids:
        # Só os metadados (sem carregar os bytes do arquivo ao listar a conversa).
        for row in db.execute(
            select(
                MessagingMedia.id,
                MessagingMedia.mime_type,
                MessagingMedia.file_name,
                MessagingMedia.size_bytes,
            ).where(
                MessagingMedia.id.in_(media_ids),
                MessagingMedia.user_id == user.id,
            )
        ).all():
            media_map[row[0]] = (row[0], row[1], row[2], row[3])
    return [
        serialize_message(
            m,
            replies.get(m.reply_to_id) if m.reply_to_id else None,
            media_map.get(m.media_id) if m.media_id else None,
        )
        for m in rows
    ]


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def list_messages(
    db: Session,
    user: User,
    chat_id: uuid.UUID,
    *,
    limit: int = 100,
    since: datetime | None = None,
) -> dict[str, Any]:
    """Sem `since`: as mais recentes. Com `since`: só o que mudou (com 5 s de sobra).

    O `cursor` devolvido é a maior data de alteração entre os itens; a tela manda de volta
    como próximo `since` e junta os itens pelo id.
    """
    chat = get_chat(db, user, chat_id)
    capped = max(1, min(limit, 300))
    base = select(MessagingMessage).where(
        MessagingMessage.chat_id == chat.id, MessagingMessage.user_id == user.id
    )
    if since is None:
        rows = list(
            db.scalars(
                base.order_by(MessagingMessage.created_at.desc(), MessagingMessage.id.desc()).limit(
                    capped
                )
            ).all()
        )
        rows.reverse()
    else:
        since = _aware(since)
        rows = list(
            db.scalars(
                base.where(MessagingMessage.updated_at >= since - SINCE_OVERLAP)
                .order_by(MessagingMessage.updated_at.asc(), MessagingMessage.id.asc())
                .limit(capped)
            ).all()
        )
        rows.sort(key=lambda m: (m.created_at, str(m.id)))

    if rows:
        cursor = max(m.updated_at for m in rows)
    else:
        cursor = since if since is not None else utcnow()
    return {"items": _serialize_with_replies(db, user, rows), "cursor": cursor}


def send_message(
    db: Session,
    user: User,
    chat_id: uuid.UUID,
    *,
    body: str,
    reply_to_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Grava a mensagem como pendente e avisa o conector para enviar já."""
    chat = get_chat(db, user, chat_id)
    text = (body or "").strip()
    if not text:
        raise AppError(400, "empty_message", "Digite uma mensagem antes de enviar.")

    session = get_or_create_session(db, user)
    if session.status != "ready":
        raise AppError(409, "whatsapp_disconnected", "Conecte o WhatsApp para enviar mensagens.")

    reply_msg: MessagingMessage | None = None
    if reply_to_id is not None:
        reply_msg = db.scalar(
            select(MessagingMessage).where(
                MessagingMessage.id == reply_to_id,
                MessagingMessage.chat_id == chat.id,
                MessagingMessage.user_id == user.id,
            )
        )
        if reply_msg is None:
            raise AppError(404, "reply_not_found", "Mensagem citada não encontrada nesta conversa.")

    now = utcnow()
    msg = MessagingMessage(
        user_id=user.id,
        chat_id=chat.id,
        direction="out",
        body=text,
        message_type="chat",
        status="pending",
        reply_to_id=reply_msg.id if reply_msg else None,
        created_at=now,
        updated_at=now,
    )
    db.add(msg)
    chat.archived = False
    chat.unread_count = 0
    chat.last_message_preview = preview(text)
    chat.last_message_at = now
    chat.updated_at = now
    db.commit()
    db.refresh(msg)
    result = serialize_message(msg, reply_msg)
    # Depois do commit: o conector busca a fila assim que recebe o aviso.
    connector_client.flush_session(session.id)
    return result


def send_media_message(
    db: Session,
    user: User,
    chat_id: uuid.UUID,
    *,
    data: bytes,
    mime_type: str,
    file_name: str | None = None,
    caption: str | None = None,
    kind: str | None = None,
    reply_to_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Grava uma mídia (foto, áudio, vídeo ou documento) na fila de envio e avisa o conector."""
    chat = get_chat(db, user, chat_id)
    session = get_or_create_session(db, user)
    if session.status != "ready":
        raise AppError(409, "whatsapp_disconnected", "Conecte o WhatsApp para enviar mensagens.")

    admin_service.assert_storage_quota(db, user, len(data))

    reply_msg: MessagingMessage | None = None
    if reply_to_id is not None:
        reply_msg = db.scalar(
            select(MessagingMessage).where(
                MessagingMessage.id == reply_to_id,
                MessagingMessage.chat_id == chat.id,
                MessagingMessage.user_id == user.id,
            )
        )
        if reply_msg is None:
            raise AppError(404, "reply_not_found", "Mensagem citada não encontrada nesta conversa.")

    media = store_media(
        db,
        user.id,
        kind=kind or "",
        mime_type=mime_type,
        data=data,
        file_name=file_name,
    )
    clean_caption = (caption or "").strip()[:4000]
    body = media_label(media.kind, media.file_name, clean_caption)
    now = utcnow()
    msg = MessagingMessage(
        user_id=user.id,
        chat_id=chat.id,
        direction="out",
        body=body,
        message_type=media.kind,
        status="pending",
        reply_to_id=reply_msg.id if reply_msg else None,
        media_id=media.id,
        created_at=now,
        updated_at=now,
    )
    db.add(msg)
    chat.archived = False
    chat.unread_count = 0
    chat.last_message_preview = preview(body)
    chat.last_message_at = now
    chat.updated_at = now
    db.commit()
    db.refresh(msg)
    result = serialize_message(
        msg,
        reply_msg,
        (media.id, media.mime_type, media.file_name, media.size_bytes),
    )
    connector_client.flush_session(session.id)
    return result
