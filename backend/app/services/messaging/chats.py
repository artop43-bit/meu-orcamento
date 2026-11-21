"""Conversas da Mensageria: lista, filtros de CRM, etiquetas, follow-up e respostas rápidas."""

import re
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.types import utcnow
from app.models import (
    MessagingChat,
    MessagingConnectorKV,
    MessagingMedia,
    MessagingMessage,
    MessagingQuickReply,
    MessagingSession,
    User,
)
from app.services.common import get_owned
from app.services.messaging import connector_client
from app.services.messaging.phones import (
    DEFAULT_CONTACT_NAME,
    digits_only,
    format_phone_display,
    normalize_phone,
)

# Confirmação de leitura enviada ao WhatsApp: só as mais recentes.
READ_RECEIPT_LIMIT = 20
SERVICE_STATUSES = ("open", "waiting", "resolved")
MAX_TAGS = 8
MAX_TAG_LEN = 24

DEFAULT_QUICK_REPLIES: list[tuple[str, str, str]] = [
    (
        "pix",
        "Enviar chave Pix",
        "Olá, {nome}! Segue minha chave Pix para transferência: {chave_pix}",
    ),
    (
        "cobranca",
        "Lembrete de valor em aberto",
        "Olá, {nome}! Tudo bem? Passando para lembrar do valor em aberto de {valor_pendente}. "
        "Qualquer dúvida estou à disposição! Chave Pix: {chave_pix}",
    ),
    (
        "boasvindas",
        "Boas-vindas e atendimento",
        "Olá, {nome}! Obrigado pelo contato. Como posso te ajudar hoje?",
    ),
    (
        "orcamento",
        "Envio de proposta / orçamento",
        "Olá, {nome}! Preparei os detalhes da sua proposta ({valor_pendente}). "
        "Ficou alguma dúvida para fecharmos?",
    ),
    (
        "retorno",
        "Follow-up amigável",
        "Olá, {nome}! Tudo certo por aí? Conseguiu avaliar nossa última conversa?",
    ),
]


def parse_chat_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for part in raw.split(","):
        clean = " ".join(part.strip().split())[:MAX_TAG_LEN]
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            out.append(clean)
            if len(out) >= MAX_TAGS:
                break
    return out


def format_chat_tags(tags: list[str] | None) -> str | None:
    if not tags:
        return None
    out: list[str] = []
    seen: set[str] = set()
    for item in tags:
        clean = " ".join(str(item).replace(",", " ").split())[:MAX_TAG_LEN]
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            out.append(clean)
            if len(out) >= MAX_TAGS:
                break
    return ",".join(out)[:240] if out else None


def list_chats(
    db: Session,
    user: User,
    *,
    q: str | None = None,
    filter_mode: str = "all",
    tag: str | None = None,
) -> list[MessagingChat]:
    stmt = select(MessagingChat).where(MessagingChat.user_id == user.id)
    if filter_mode == "archived":
        stmt = stmt.where(MessagingChat.archived.is_(True))
    else:
        stmt = stmt.where(MessagingChat.archived.is_(False))
        if filter_mode == "unread":
            stmt = stmt.where(MessagingChat.unread_count > 0)
        elif filter_mode == "followup":
            stmt = stmt.where(MessagingChat.followup_at.is_not(None))
        elif filter_mode in SERVICE_STATUSES:
            stmt = stmt.where(MessagingChat.service_status == filter_mode)

    clean_tag = (tag or "").strip().lower()
    if clean_tag:
        stmt = stmt.where(MessagingChat.tags.ilike(f"%{clean_tag}%"))

    term = (q or "").strip()
    if term:
        like = f"%{term}%"
        digits = digits_only(term)
        conditions = [
            MessagingChat.name.ilike(like),
            MessagingChat.phone.ilike(like),
            MessagingChat.last_message_preview.ilike(like),
            MessagingChat.budget_person.ilike(like),
            MessagingChat.tags.ilike(like),
            MessagingChat.followup_note.ilike(like),
        ]
        if digits:
            conditions.append(MessagingChat.phone.ilike(f"%{digits}%"))
        stmt = stmt.where(or_(*conditions))

    stmt = stmt.order_by(
        MessagingChat.pinned.desc(),
        MessagingChat.last_message_at.desc().nullslast(),
        MessagingChat.created_at.desc(),
    )
    rows = list(db.scalars(stmt).all())
    if clean_tag:
        rows = [
            row for row in rows if any(t.lower() == clean_tag for t in parse_chat_tags(row.tags))
        ]
    return rows


def get_chat(db: Session, user: User, chat_id: uuid.UUID) -> MessagingChat:
    return get_owned(
        db,
        MessagingChat,
        user.id,
        chat_id,
        error_code="chat_not_found",
        error_msg="Conversa não encontrada.",
    )


def create_or_open_chat(
    db: Session,
    user: User,
    *,
    phone: str,
    name: str | None = None,
    notes: str | None = None,
    budget_person: str | None = None,
) -> tuple[MessagingChat, bool]:
    digits, remote_jid = normalize_phone(phone)
    match = [MessagingChat.remote_jid == remote_jid]
    if digits is None:
        match.append(MessagingChat.lid_jid == remote_jid)
    existing = db.scalar(
        select(MessagingChat)
        .where(MessagingChat.user_id == user.id, or_(*match))
        .order_by(MessagingChat.created_at)
        .limit(1)
    )
    clean_name = (name or "").strip()[:120]
    clean_notes = (notes or "").strip()[:300] or None
    clean_person = (budget_person or "").strip()[:80] or None

    if existing is not None:
        changed = False
        if existing.archived:
            existing.archived = False
            changed = True
        if clean_name and (existing.name != clean_name or existing.name_source != "manual"):
            existing.name = clean_name
            existing.name_source = "manual"
            changed = True
        if notes is not None and existing.notes != clean_notes:
            existing.notes = clean_notes
            changed = True
        if budget_person is not None and existing.budget_person != clean_person:
            existing.budget_person = clean_person
            changed = True
        if changed:
            existing.updated_at = utcnow()
            db.commit()
            db.refresh(existing)
        return existing, False

    chat = MessagingChat(
        user_id=user.id,
        remote_jid=remote_jid,
        phone=digits,
        lid_jid=remote_jid if digits is None else None,
        name=clean_name or format_phone_display(digits) or DEFAULT_CONTACT_NAME,
        name_source="manual" if clean_name else "fallback",
        notes=clean_notes,
        budget_person=clean_person,
    )
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return chat, True


def update_chat(
    db: Session,
    user: User,
    chat_id: uuid.UUID,
    changes: dict[str, Any],
) -> MessagingChat:
    chat = get_chat(db, user, chat_id)
    if "name" in changes and changes["name"] is not None:
        clean = str(changes["name"]).strip()[:120]
        if not clean:
            raise AppError(400, "invalid_name", "Informe o nome do contato.")
        chat.name = clean
        chat.name_source = "manual"
    if "notes" in changes:
        chat.notes = (str(changes["notes"]).strip()[:300] or None) if changes["notes"] else None
    if "budget_person" in changes:
        chat.budget_person = (
            (str(changes["budget_person"]).strip()[:80] or None)
            if changes["budget_person"]
            else None
        )
    if "tags" in changes:
        chat.tags = format_chat_tags(changes["tags"])
    if "service_status" in changes and changes["service_status"] is not None:
        st = str(changes["service_status"]).strip().lower()
        if st not in SERVICE_STATUSES:
            raise AppError(400, "invalid_status", "Status de atendimento inválido.")
        chat.service_status = st
    if "followup_at" in changes:
        val = changes["followup_at"]
        if val is None or isinstance(val, datetime):
            chat.followup_at = val
    if "followup_note" in changes:
        note = changes["followup_note"]
        chat.followup_note = (str(note).strip()[:200] or None) if note else None
    if "pinned" in changes and changes["pinned"] is not None:
        chat.pinned = bool(changes["pinned"])
    if "archived" in changes and changes["archived"] is not None:
        chat.archived = bool(changes["archived"])
    chat.updated_at = utcnow()
    db.commit()
    db.refresh(chat)
    return chat


def delete_chat(db: Session, user: User, chat_id: uuid.UUID) -> None:
    chat = get_chat(db, user, chat_id)
    media_ids = list(
        db.scalars(
            select(MessagingMessage.media_id).where(
                MessagingMessage.chat_id == chat.id,
                MessagingMessage.media_id.is_not(None),
            )
        ).all()
    )
    db.execute(
        update(MessagingMessage)
        .where(MessagingMessage.chat_id == chat.id)
        .values(reply_to_id=None, media_id=None)
    )
    db.execute(delete(MessagingMessage).where(MessagingMessage.chat_id == chat.id))
    if media_ids:
        db.execute(
            delete(MessagingMedia).where(
                MessagingMedia.user_id == user.id,
                MessagingMedia.id.in_(media_ids),
            )
        )
    db.delete(chat)
    db.commit()


def chat_avatar_url(chat: MessagingChat) -> str | None:
    if not chat.avatar_mime:
        return None
    stamp = int((chat.avatar_updated_at or chat.updated_at).timestamp())
    return f"/api/messaging/chats/{chat.id}/avatar?v={stamp}"


def get_chat_avatar(db: Session, user: User, chat_id: uuid.UUID) -> tuple[bytes, str]:
    chat = get_chat(db, user, chat_id)
    if not chat.avatar_data or not chat.avatar_mime:
        raise AppError(404, "avatar_not_found", "Contato sem foto de perfil.")
    return chat.avatar_data, chat.avatar_mime


def mark_chat_read(db: Session, user: User, chat_id: uuid.UUID) -> MessagingChat:
    """Zera as não lidas e, com o WhatsApp conectado, confirma a leitura no celular também."""
    chat = get_chat(db, user, chat_id)
    unread = chat.unread_count or 0
    external_ids: list[str] = []
    if unread > 0:
        latest = db.scalars(
            select(MessagingMessage.external_id)
            .where(
                MessagingMessage.chat_id == chat.id,
                MessagingMessage.user_id == user.id,
                MessagingMessage.direction == "in",
                MessagingMessage.external_id.is_not(None),
            )
            .order_by(MessagingMessage.created_at.desc())
            .limit(min(unread, READ_RECEIPT_LIMIT))
        ).all()
        external_ids = [ext for ext in reversed(latest) if ext]
        chat.unread_count = 0
        chat.updated_at = utcnow()
        db.commit()
        db.refresh(chat)

    if external_ids:
        session = db.scalar(select(MessagingSession).where(MessagingSession.user_id == user.id))
        if session is not None and session.status == "ready":
            connector_client.mark_read(session.id, chat.remote_jid, external_ids)
    return chat


# ---------------------------------------------------------------- respostas rápidas


def _clean_shortcut(raw: str) -> str:
    clean = re.sub(r"[^a-z0-9_-]+", "", raw.strip().lstrip("/").lower())[:40]
    if not clean:
        raise AppError(
            400,
            "invalid_shortcut",
            "Informe um atalho válido (letras e números, ex.: pix ou cobranca).",
        )
    return clean


def list_quick_replies(db: Session, user: User) -> list[MessagingQuickReply]:
    rows = list(
        db.scalars(
            select(MessagingQuickReply)
            .where(MessagingQuickReply.user_id == user.id)
            .order_by(MessagingQuickReply.shortcut.asc())
        ).all()
    )
    seed_key = f"quick_replies_seeded:{user.id}"
    if db.get(MessagingConnectorKV, seed_key) is None:
        db.add(MessagingConnectorKV(key=seed_key, value="1"))
        if rows:
            db.commit()
            return rows
        for shortcut, title, body in DEFAULT_QUICK_REPLIES:
            db.add(
                MessagingQuickReply(
                    user_id=user.id,
                    shortcut=shortcut,
                    title=title,
                    body=body,
                )
            )
        db.commit()
        rows = list(
            db.scalars(
                select(MessagingQuickReply)
                .where(MessagingQuickReply.user_id == user.id)
                .order_by(MessagingQuickReply.shortcut.asc())
            ).all()
        )
    return rows


def create_quick_reply(
    db: Session,
    user: User,
    *,
    shortcut: str,
    title: str,
    body: str,
) -> MessagingQuickReply:
    clean_sc = _clean_shortcut(shortcut)
    clean_title = title.strip()[:80]
    clean_body = body.strip()[:2000]
    if not clean_title or not clean_body:
        raise AppError(400, "invalid_quick_reply", "Informe o título e o texto do atalho.")
    existing = db.scalar(
        select(MessagingQuickReply).where(
            MessagingQuickReply.user_id == user.id,
            MessagingQuickReply.shortcut == clean_sc,
        )
    )
    if existing is not None:
        raise AppError(409, "quick_reply_exists", "Já existe uma resposta com esse atalho.")

    item = MessagingQuickReply(
        user_id=user.id,
        shortcut=clean_sc,
        title=clean_title,
        body=clean_body,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def delete_quick_reply(db: Session, user: User, reply_id: uuid.UUID) -> None:
    item = get_owned(
        db,
        MessagingQuickReply,
        user.id,
        reply_id,
        error_code="quick_reply_not_found",
        error_msg="Atalho não encontrado.",
    )
    db.delete(item)
    db.commit()
