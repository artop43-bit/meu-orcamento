"""Aplicação em lote dos eventos recebidos do conector (status, mensagem, recibo, ack, avatar)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.types import utcnow
from app.models import MessagingMedia, MessagingMessage, MessagingSession, User
from app.services.messaging.connector.chats import (
    maybe_upgrade_name,
    resolve_chat,
    resolve_chat_with_meta,
)
from app.services.messaging.connector.events import (
    EVENT_ADAPTER,
    MAX_BODY,
    STATUS_RANK,
    UNSUPPORTED_BODY,
    AckEvent,
    ContactEvent,
    MediaAttachEvent,
    MessageEvent,
    ReadSelfEvent,
    ReceiptEvent,
    StatusEvent,
    aware_utc,
    clean_text,
    normalize_message_type,
)
from app.services.messaging.media import INLINE_IMAGE_MIMES, MAX_AVATAR_BYTES, clean_mime_type
from app.services.messaging.messages import preview
from app.services.messaging.phones import digits_only, phone_from_jid, split_jids

logger = logging.getLogger(__name__)
MAX_EVENTS = 500


def _apply_status(db: Session, user: User, session: MessagingSession, ev: StatusEvent) -> bool:
    if ev.wanted is False:
        session.wanted = False
    # Pedido antigo: a pessoa já desconectou (ou o QR expirou) e o conector ainda não sabia.
    if not session.wanted and ev.status in {"qr", "connecting", "ready"}:
        return False

    session.status = ev.status
    session.last_seen_at = utcnow()
    session.qr_code = ((ev.qr or "").strip()[:8000] or None) if ev.status == "qr" else None
    if ev.wa_jid is not None:
        session.wa_jid = ev.wa_jid.strip()[:64] or None
    phone = digits_only(ev.phone)[:32] if ev.phone else phone_from_jid(ev.wa_jid)
    if phone:
        session.phone = phone
    if ev.display_name is not None:
        session.display_name = clean_text(ev.display_name, 120) or None
    error = (ev.error or "").strip()[:300]
    if error:
        session.last_error = error
    elif ev.status == "error":
        session.last_error = "Erro na conexão com o WhatsApp."
    else:
        session.last_error = None
    return True


def _apply_message(db: Session, user: User, session: MessagingSession, ev: MessageEvent) -> bool:
    external_id = ev.external_id.strip()
    if not external_id:
        return False
    duplicate = db.scalar(
        select(MessagingMessage.id).where(
            MessagingMessage.user_id == user.id,
            MessagingMessage.external_id == external_id,
        )
    )
    if duplicate is not None:
        return False
    pn, lid = split_jids(ev.remote_jid, ev.remote_jid_alt)
    if pn is None and lid is None:
        return False

    push_name = "" if ev.from_me else clean_text(ev.push_name, 120)
    chat = resolve_chat(db, user, pn, lid, push_name=push_name, create=True)
    if chat is None:
        return False

    now = utcnow()
    when = aware_utc(ev.timestamp) or now
    text = (ev.body or "").strip()[:MAX_BODY] or UNSUPPORTED_BODY
    reply_id = None
    if ev.quoted_external_id and ev.quoted_external_id.strip():
        reply_id = db.scalar(
            select(MessagingMessage.id).where(
                MessagingMessage.user_id == user.id,
                MessagingMessage.chat_id == chat.id,
                MessagingMessage.external_id == ev.quoted_external_id.strip(),
            )
        )
    media_id = None
    if ev.media_id is not None:
        owned = db.scalar(
            select(MessagingMedia.id).where(
                MessagingMedia.id == ev.media_id,
                MessagingMedia.user_id == user.id,
            )
        )
        if owned is not None:
            media_id = owned

    if ev.from_me:
        raw_status = "read" if ev.status == "played" else (ev.status or "sent")
        msg_status = raw_status if raw_status in STATUS_RANK else "sent"
    else:
        msg_status = "delivered"

    db.add(
        MessagingMessage(
            user_id=user.id,
            chat_id=chat.id,
            direction="out" if ev.from_me else "in",
            body=text,
            message_type=normalize_message_type(ev.message_type),
            status=msg_status,
            external_id=external_id,
            reply_to_id=reply_id,
            media_id=media_id,
            sent_at=when,
            created_at=when,
            updated_at=now,
        )
    )
    # Só o que chega agora conta como não lida (histórico e as minhas, não).
    if not ev.from_me and not ev.history:
        chat.unread_count = (chat.unread_count or 0) + 1
        chat.archived = False
    if chat.last_message_at is None or when >= chat.last_message_at:
        chat.last_message_preview = preview(text)
        chat.last_message_at = when
    chat.updated_at = now
    db.flush()
    return True


def _apply_receipt(db: Session, user: User, session: MessagingSession, ev: ReceiptEvent) -> bool:
    msg = db.scalar(
        select(MessagingMessage).where(
            MessagingMessage.user_id == user.id,
            MessagingMessage.external_id == ev.external_id.strip(),
            MessagingMessage.direction == "out",
        )
    )
    if msg is None:
        return False
    now = utcnow()
    status = "read" if ev.status == "played" else ev.status
    if status == "failed":
        # Falha só vale enquanto não foi entregue.
        if msg.status not in {"pending", "sent"}:
            return False
        msg.status = "failed"
        msg.error_detail = (ev.error or "").strip()[:300] or "O WhatsApp não entregou a mensagem."
    else:
        if STATUS_RANK[status] <= STATUS_RANK.get(msg.status, 0):
            return False
        msg.status = status
        msg.error_detail = None
        if msg.sent_at is None:
            msg.sent_at = now
    msg.updated_at = now
    return True


def _apply_ack(db: Session, user: User, session: MessagingSession, ev: AckEvent) -> bool:
    msg = db.scalar(
        select(MessagingMessage).where(
            MessagingMessage.id == ev.message_id,
            MessagingMessage.user_id == user.id,
            MessagingMessage.direction == "out",
        )
    )
    if msg is None:
        return False
    now = utcnow()
    msg.claimed_at = None
    if ev.status == "sent":
        external_id = (ev.external_id or "").strip() or None
        if external_id and external_id != msg.external_id:
            clash = db.scalar(
                select(MessagingMessage).where(
                    MessagingMessage.user_id == user.id,
                    MessagingMessage.external_id == external_id,
                    MessagingMessage.id != msg.id,
                )
            )
            if clash is not None and clash.direction == "out" and clash.chat_id == msg.chat_id:
                # A mesma mensagem já tinha chegado como evento: fica só a da fila, e quem
                # citava a cópia passa a citar a da fila.
                db.execute(
                    update(MessagingMessage)
                    .where(MessagingMessage.reply_to_id == clash.id)
                    .values(reply_to_id=msg.id, updated_at=now)
                )
                db.delete(clash)
                db.flush()
                clash = None
            if clash is None:
                msg.external_id = external_id
        if STATUS_RANK.get(msg.status, 0) < STATUS_RANK["sent"]:
            msg.status = "sent"
        if msg.sent_at is None:
            msg.sent_at = now
        msg.error_detail = None
    elif msg.status in {"pending", "failed"}:
        msg.status = "failed"
        msg.error_detail = (ev.error or "").strip()[:300] or "Não foi possível enviar a mensagem."
    # Falha de uma tentativa repetida de algo que já saiu: só libera a reserva.
    msg.updated_at = now
    return True


def _apply_read_self(db: Session, user: User, session: MessagingSession, ev: ReadSelfEvent) -> bool:
    pn, lid = split_jids(ev.remote_jid, ev.remote_jid_alt)
    chat = resolve_chat(db, user, pn, lid, create=False)
    if chat is None:
        return False
    if chat.unread_count:
        chat.unread_count = 0
        chat.updated_at = utcnow()
    return True


def _apply_media_attach(
    db: Session, user: User, session: MessagingSession, ev: MediaAttachEvent
) -> bool:
    """Liga uma mídia baixada em segundo plano à mensagem já gravada (atualiza updated_at)."""
    msg = db.scalar(
        select(MessagingMessage).where(
            MessagingMessage.user_id == user.id,
            MessagingMessage.external_id == ev.external_id.strip(),
        )
    )
    if msg is None:
        return False
    owned = db.scalar(
        select(MessagingMedia.id).where(
            MessagingMedia.id == ev.media_id,
            MessagingMedia.user_id == user.id,
        )
    )
    if owned is None:
        return False
    if msg.media_id == owned:
        return False
    msg.media_id = owned
    msg.updated_at = utcnow()
    return True


def _apply_contact(db: Session, user: User, session: MessagingSession, ev: ContactEvent) -> bool:
    name = clean_text(ev.name, 120)
    pn, lid = split_jids(ev.jid, ev.jid_alt)
    if pn is None and lid is None:
        return False
    chat, linked = resolve_chat_with_meta(db, user, pn, lid, create=False)
    if chat is None:
        return False
    mapped_source = "contact" if ev.source in {"contact", "chat"} else "push"
    renamed = maybe_upgrade_name(chat, name, mapped_source) if name else False
    if not linked and not renamed:
        return False
    chat.updated_at = utcnow()
    return True


_HANDLERS: dict[str, Any] = {
    "status": _apply_status,
    "message": _apply_message,
    "media_attach": _apply_media_attach,
    "receipt": _apply_receipt,
    "ack": _apply_ack,
    "read_self": _apply_read_self,
    "contact": _apply_contact,
}


def _session_context(
    db: Session,
    cache: dict[uuid.UUID, tuple[MessagingSession, User] | None],
    session_id: uuid.UUID,
) -> tuple[MessagingSession, User] | None:
    if session_id not in cache:
        row = db.execute(
            select(MessagingSession, User)
            .join(User, User.id == MessagingSession.user_id)
            .where(MessagingSession.id == session_id)
        ).first()
        # Conta bloqueada: os eventos da sessão são ignorados.
        if row is None or row[1].access_status == "blocked":
            cache[session_id] = None
        else:
            cache[session_id] = (row[0], row[1])
    return cache[session_id]


def process_events(db: Session, events: list[dict[str, Any]]) -> dict[str, int]:
    """Aplica os eventos em ordem; um evento com erro não derruba os outros do lote."""
    processed = 0
    ignored = 0
    contexts: dict[uuid.UUID, tuple[MessagingSession, User] | None] = {}
    touched: set[uuid.UUID] = set()
    for raw in events[:MAX_EVENTS]:
        try:
            event = EVENT_ADAPTER.validate_python(raw)
        except ValidationError as exc:
            kind = raw.get("type") if isinstance(raw, dict) else None
            logger.warning("Evento do conector inválido (%s): %s", kind, exc.error_count())
            ignored += 1
            continue
        context = _session_context(db, contexts, event.session_id)
        if context is None:
            ignored += 1
            continue
        session, user = context
        try:
            # Ponto de salvamento: se o evento falhar, só ele é desfeito.
            with db.begin_nested():
                applied = bool(_HANDLERS[event.type](db, user, session, event))
        except Exception:
            logger.exception("Falha ao aplicar evento %s do conector", event.type)
            applied = False
        if applied:
            processed += 1
            touched.add(session.id)
        else:
            ignored += 1

    now = utcnow()
    for session_id in touched:
        context = contexts.get(session_id)
        if context is not None:
            context[0].last_seen_at = now
    db.commit()
    return {"processed": processed, "ignored": ignored}


def save_connector_avatar(
    db: Session,
    session_id: uuid.UUID,
    *,
    jid: str,
    jid_alt: str | None = None,
    mime_type: str,
    data: bytes,
) -> bool:
    """Salva a foto de perfil de um contato existente (enviada pelo conector)."""
    if not data or len(data) > MAX_AVATAR_BYTES:
        status_code = 413 if len(data) > MAX_AVATAR_BYTES else 400
        raise AppError(status_code, "invalid_avatar", "Foto inválida.")
    safe_mime = clean_mime_type(mime_type)
    if safe_mime not in INLINE_IMAGE_MIMES:
        raise AppError(400, "invalid_avatar", "Formato de foto não suportado.")
    context = _session_context(db, {}, session_id)
    if context is None:
        return False
    _, user = context
    pn, lid = split_jids(jid, jid_alt)
    if pn is None and lid is None:
        return False
    chat = resolve_chat(db, user, pn, lid, create=False)
    if chat is None:
        return False
    now = utcnow()
    chat.avatar_data = data
    chat.avatar_mime = safe_mime
    chat.avatar_updated_at = now
    chat.updated_at = now
    db.commit()
    return True
