"""Resolução e fusão de conversas do WhatsApp a partir de JID (número) e LID."""

from __future__ import annotations

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.db.types import utcnow
from app.models import CrmContact, MessagingChat, MessagingMessage, User
from app.services.messaging.connector.events import NAME_SOURCE_RANK, clean_text
from app.services.messaging.phones import (
    DEFAULT_CONTACT_NAME,
    LID_SUFFIX,
    digits_only,
    format_phone_display,
    is_placeholder_name,
    phone_from_jid,
)


def has_generic_name(chat: MessagingChat) -> bool:
    """Nome que não veio da pessoa: o número formatado, mascarado ou 'Contato do WhatsApp'."""
    name = (chat.name or "").strip()
    if is_placeholder_name(name):
        return True
    if chat.phone and name == format_phone_display(chat.phone):
        return True
    # Conversas antigas com LID ganhavam "+<dígitos do LID>" como nome.
    return any(
        jid and name == format_phone_display(digits_only(jid.split("@", 1)[0]))
        for jid in (chat.remote_jid, chat.lid_jid)
    )


def effective_name_rank(chat: MessagingChat) -> int:
    if has_generic_name(chat):
        return 0
    return NAME_SOURCE_RANK.get(chat.name_source or "fallback", 1)


def maybe_upgrade_name(chat: MessagingChat, candidate: str, source: str) -> bool:
    """Troca o nome só se a nova origem vencer (manual > agenda > apelido > genérico)."""
    cleaned = clean_text(candidate, 120)
    if not cleaned or is_placeholder_name(cleaned):
        return False
    incoming_rank = NAME_SOURCE_RANK.get(source, 0)
    current_rank = effective_name_rank(chat)
    if incoming_rank <= current_rank:
        return False
    if chat.name == cleaned and chat.name_source == source:
        return False
    chat.name = cleaned
    chat.name_source = source
    return True


def merge_chat(db: Session, primary: MessagingChat, other: MessagingChat) -> None:
    """Junta numa conversa só a do número e a do LID da mesma pessoa."""
    db.execute(
        update(MessagingMessage)
        .where(MessagingMessage.chat_id == other.id)
        .values(chat_id=primary.id, updated_at=utcnow())
    )
    primary.unread_count = (primary.unread_count or 0) + (other.unread_count or 0)
    primary.pinned = bool(primary.pinned or other.pinned)
    primary.archived = bool(primary.archived and other.archived)
    primary.tags = (
        ",".join(
            dict.fromkeys(
                tag.strip()
                for raw in (primary.tags, other.tags)
                for tag in (raw or "").split(",")
                if tag.strip()
            )
        )
        or None
    )
    if primary.service_status == "open" and other.service_status != "open":
        primary.service_status = other.service_status
    if other.followup_at is not None and (
        primary.followup_at is None or other.followup_at < primary.followup_at
    ):
        primary.followup_at = other.followup_at
        primary.followup_note = other.followup_note or primary.followup_note
    elif not primary.followup_note:
        primary.followup_note = other.followup_note
    db.execute(
        update(CrmContact)
        .where(CrmContact.messaging_chat_id == other.id)
        .values(messaging_chat_id=primary.id)
    )
    if not primary.notes and other.notes:
        primary.notes = other.notes
    if not primary.budget_person and other.budget_person:
        primary.budget_person = other.budget_person
    if effective_name_rank(other) > effective_name_rank(primary):
        primary.name = other.name
        primary.name_source = other.name_source
    if not primary.avatar_data and other.avatar_data:
        primary.avatar_data = other.avatar_data
        primary.avatar_mime = other.avatar_mime
        primary.avatar_updated_at = other.avatar_updated_at
    if other.last_message_at is not None and (
        primary.last_message_at is None or other.last_message_at > primary.last_message_at
    ):
        primary.last_message_at = other.last_message_at
        primary.last_message_preview = other.last_message_preview
    if not primary.phone and other.phone:
        primary.phone = other.phone
    if not primary.lid_jid and other.lid_jid:
        primary.lid_jid = other.lid_jid
    db.delete(other)
    # Apaga já: a conversa principal pode assumir o endereço da que saiu.
    db.flush()


def resolve_chat_with_meta(
    db: Session,
    user: User,
    pn: str | None,
    lid: str | None,
    *,
    push_name: str = "",
    name_source: str = "push",
    create: bool,
) -> tuple[MessagingChat | None, bool]:
    """Acha (ou cria) a conversa por número/LID; devolve (conversa, houve_vinculo_ou_fusao)."""
    jids = [jid for jid in (pn, lid) if jid]
    if not jids:
        return None, False
    match = [MessagingChat.remote_jid.in_(jids)]
    if lid:
        match.append(MessagingChat.lid_jid == lid)
    chats = list(
        db.scalars(
            select(MessagingChat)
            .where(MessagingChat.user_id == user.id, or_(*match))
            .order_by(MessagingChat.created_at, MessagingChat.id)
        ).all()
    )

    valid_push = "" if is_placeholder_name(push_name) else clean_text(push_name, 120)

    if not chats:
        if not create:
            return None, False
        phone = phone_from_jid(pn)
        if valid_push:
            initial_name = valid_push
            initial_source = name_source if name_source in NAME_SOURCE_RANK else "push"
        else:
            initial_name = format_phone_display(phone) or DEFAULT_CONTACT_NAME
            initial_source = "fallback"
        chat = MessagingChat(
            user_id=user.id,
            remote_jid=pn or lid,
            phone=phone,
            lid_jid=lid,
            name=initial_name,
            name_source=initial_source,
            unread_count=0,
            pinned=False,
            archived=False,
        )
        db.add(chat)
        db.flush()
        return chat, True

    linked = False
    primary = next((c for c in chats if pn and c.remote_jid == pn), chats[0])
    for other in chats:
        if other is not primary:
            merge_chat(db, primary, other)
            linked = True

    if pn:
        # Com o número conhecido, ele vira o endereço de envio da conversa.
        if primary.remote_jid.endswith(LID_SUFFIX):
            primary.remote_jid = pn
            linked = True
        if not primary.phone:
            primary.phone = phone_from_jid(pn)
            linked = True
    if lid and not primary.lid_jid:
        primary.lid_jid = lid
        linked = True

    if valid_push and maybe_upgrade_name(primary, valid_push, name_source):
        linked = True
    elif has_generic_name(primary) and primary.phone:
        formatted = format_phone_display(primary.phone)
        if formatted and primary.name != formatted:
            primary.name = formatted
            primary.name_source = "fallback"
            linked = True

    db.flush()
    return primary, linked


def resolve_chat(
    db: Session,
    user: User,
    pn: str | None,
    lid: str | None,
    *,
    push_name: str = "",
    name_source: str = "push",
    create: bool,
) -> MessagingChat | None:
    chat, _ = resolve_chat_with_meta(
        db, user, pn, lid, push_name=push_name, name_source=name_source, create=create
    )
    return chat
