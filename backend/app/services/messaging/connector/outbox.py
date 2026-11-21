"""Autenticação, sessões ativas e reserva de mensagens na fila de envio (outbox)."""

from __future__ import annotations

import hmac
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.types import utcnow
from app.models import MessagingChat, MessagingMedia, MessagingMessage, MessagingSession, User
from app.services.messaging.media import MEDIA_LABELS
from app.services.messaging.sessions import connector_unavailable

# Item reservado e sem resposta do conector volta para a fila depois disso.
OUTBOX_CLAIM_SECONDS = 60
MAX_OUTBOX_SESSIONS = 200
MAX_OUTBOX_LIMIT = 100


def _extract_media_caption(body: str, kind: str, file_name: str | None) -> str:
    prefix = MEDIA_LABELS.get(kind, "")
    text = (body or "").strip()
    if not prefix or not text.startswith(prefix):
        return text
    rest = text[len(prefix) :].strip()
    if not rest.startswith("·"):
        return ""
    rest = rest[1:].strip()
    if kind == "document" and file_name and rest.startswith(file_name):
        after = rest[len(file_name) :].strip()
        if not after:
            return ""
        if after.startswith("·"):
            return after[1:].strip()
    return rest


def authenticate_connector(raw_token: str | None) -> None:
    expected = get_settings().messaging_connector_token.strip()
    if not expected:
        raise connector_unavailable()
    given = (raw_token or "").strip()
    if not given or not hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8")):
        raise AppError(401, "connector_unauthorized", "Chave do conector inválida.")


def list_connector_sessions(db: Session) -> list[dict[str, str]]:
    """Sessões que a pessoa pediu para manter conectadas (o conector restaura ao ligar)."""
    ids = db.scalars(
        select(MessagingSession.id)
        .join(User, User.id == MessagingSession.user_id)
        .where(MessagingSession.wanted.is_(True), User.access_status != "blocked")
        .order_by(MessagingSession.created_at, MessagingSession.id)
    ).all()
    return [{"session_id": str(session_id)} for session_id in ids]


def parse_session_ids(raw: str | None) -> list[uuid.UUID]:
    parts = [part.strip() for part in (raw or "").split(",") if part.strip()]
    if len(parts) > MAX_OUTBOX_SESSIONS:
        raise AppError(
            400, "too_many_sessions", f"Peça no máximo {MAX_OUTBOX_SESSIONS} sessões por vez."
        )
    try:
        ids = [uuid.UUID(part) for part in parts]
    except ValueError as exc:
        raise AppError(400, "invalid_session_id", "Identificador de sessão inválido.") from exc
    return list(dict.fromkeys(ids))


def claim_outbox(
    db: Session, session_ids: list[uuid.UUID], *, limit: int = 50
) -> list[dict[str, Any]]:
    """Entrega e reserva as mensagens pendentes das sessões prontas (evita envio duplo)."""
    if not session_ids:
        return []
    now = utcnow()
    stale = now - timedelta(seconds=OUTBOX_CLAIM_SECONDS)
    capped = max(1, min(limit, MAX_OUTBOX_LIMIT))
    rows = db.execute(
        select(MessagingMessage, MessagingChat.remote_jid, MessagingSession.id)
        .join(MessagingChat, MessagingChat.id == MessagingMessage.chat_id)
        .join(MessagingSession, MessagingSession.user_id == MessagingMessage.user_id)
        .join(User, User.id == MessagingMessage.user_id)
        .where(
            MessagingSession.id.in_(session_ids),
            MessagingSession.status == "ready",
            MessagingSession.wanted.is_(True),
            User.access_status != "blocked",
            MessagingMessage.direction == "out",
            MessagingMessage.status == "pending",
            or_(MessagingMessage.claimed_at.is_(None), MessagingMessage.claimed_at < stale),
        )
        .order_by(MessagingMessage.created_at.asc(), MessagingMessage.id.asc())
        .limit(capped)
        .with_for_update(of=MessagingMessage, skip_locked=True)
    ).all()

    reply_ids = {msg.reply_to_id for msg, _, _ in rows if msg.reply_to_id is not None}
    quoted: dict[uuid.UUID, dict[str, Any]] = {}
    if reply_ids:
        for ref, ref_jid in db.execute(
            select(MessagingMessage, MessagingChat.remote_jid)
            .join(MessagingChat, MessagingChat.id == MessagingMessage.chat_id)
            .where(MessagingMessage.id.in_(reply_ids))
        ).all():
            # Sem o id do WhatsApp não dá para citar (ex.: a citada nunca chegou a sair).
            if ref.external_id:
                quoted[ref.id] = {
                    "external_id": ref.external_id,
                    "from_me": ref.direction == "out",
                    "remote_jid": ref_jid,
                    "body": ref.body,
                }

    media_ids = {msg.media_id for msg, _, _ in rows if msg.media_id is not None}
    media_map: dict[uuid.UUID, dict[str, Any]] = {}
    if media_ids:
        for row in db.execute(
            select(
                MessagingMedia.id,
                MessagingMedia.kind,
                MessagingMedia.mime_type,
                MessagingMedia.file_name,
            ).where(MessagingMedia.id.in_(media_ids))
        ).all():
            media_map[row[0]] = {
                "media_id": row[0],
                "kind": row[1],
                "mime_type": row[2],
                "file_name": row[3],
            }

    items: list[dict[str, Any]] = []
    for msg, remote_jid, session_id in rows:
        media_info = media_map.get(msg.media_id) if msg.media_id else None
        caption = (
            _extract_media_caption(msg.body, media_info["kind"], media_info["file_name"])
            if media_info
            else None
        )
        items.append(
            {
                "message_id": msg.id,
                "session_id": session_id,
                "remote_jid": remote_jid,
                "body": msg.body,
                "message_type": msg.message_type,
                "media": media_info,
                "caption": caption,
                "quoted": quoted.get(msg.reply_to_id) if msg.reply_to_id else None,
                "created_at": msg.created_at,
            }
        )
        msg.claimed_at = now
        msg.updated_at = now
    db.commit()
    return items
