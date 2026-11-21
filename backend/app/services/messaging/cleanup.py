"""Limpeza semanal automática das conversas e mídias da Mensageria (7 dias).

Apaga apenas a cópia guardada no servidor do Hub — nunca apaga nada no WhatsApp do celular.
Conversas fixadas continuam na lista mesmo quando suas mensagens antigas expiram.
"""

from datetime import timedelta

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.db.types import utcnow
from app.models import (
    CrmContact,
    MessagingChat,
    MessagingMedia,
    MessagingMessage,
    NotebookNote,
    VaultDocument,
)
from app.services.messaging.messages import preview

RETENTION = timedelta(days=7)


def purge_old(db: Session, *, retention: timedelta = RETENTION) -> dict[str, int]:
    """Remove mensagens e mídias com mais de 7 dias e conversas sem atividade no período."""
    now = utcnow()
    cutoff = now - retention

    old_msg_rows = db.execute(
        select(MessagingMessage.id, MessagingMessage.chat_id, MessagingMessage.media_id).where(
            MessagingMessage.created_at < cutoff
        )
    ).all()
    old_msg_ids = [row[0] for row in old_msg_rows]
    affected_chat_ids = {row[1] for row in old_msg_rows}
    expired_media_ids = {row[2] for row in old_msg_rows if row[2] is not None}

    removed_messages = 0
    if old_msg_ids:
        # SQLite pode não aplicar ON DELETE SET NULL: solta citações antes de apagar.
        db.execute(
            update(MessagingMessage)
            .where(MessagingMessage.reply_to_id.in_(old_msg_ids))
            .values(reply_to_id=None, updated_at=now)
        )
        removed_messages = db.execute(
            delete(MessagingMessage).where(MessagingMessage.id.in_(old_msg_ids))
        ).rowcount

    old_media_ids = set(
        db.scalars(select(MessagingMedia.id).where(MessagingMedia.created_at < cutoff)).all()
    )
    media_to_delete = expired_media_ids | old_media_ids
    removed_media = 0
    if media_to_delete:
        db.execute(
            update(MessagingMessage)
            .where(MessagingMessage.media_id.in_(media_to_delete))
            .values(media_id=None, updated_at=now)
        )
        # Mantém a cópia permanente do Cofre intacta mesmo no SQLite sem FK cascata.
        db.execute(
            update(VaultDocument)
            .where(VaultDocument.messaging_media_id.in_(media_to_delete))
            .values(messaging_media_id=None, updated_at=now)
        )
        removed_media = db.execute(
            delete(MessagingMedia).where(MessagingMedia.id.in_(media_to_delete))
        ).rowcount

    # Atualiza prévia e data das conversas que tiveram mensagens antigas removidas.
    for chat_id in affected_chat_ids:
        chat = db.get(MessagingChat, chat_id)
        if chat is None:
            continue
        latest = db.scalar(
            select(MessagingMessage)
            .where(MessagingMessage.chat_id == chat_id)
            .order_by(MessagingMessage.created_at.desc(), MessagingMessage.id.desc())
            .limit(1)
        )
        if latest is None:
            chat.last_message_preview = None
            chat.unread_count = 0
        else:
            chat.last_message_at = latest.created_at
            chat.last_message_preview = preview(latest.body)
        chat.updated_at = now
    db.flush()

    # Apaga conversas não fixadas que ficaram sem mensagens e inativas há mais de 7 dias.
    chats_with_messages = select(MessagingMessage.chat_id).distinct()
    stale_chat_ids = list(
        db.scalars(
            select(MessagingChat.id).where(
                MessagingChat.pinned.is_(False),
                MessagingChat.followup_at.is_(None),
                func.coalesce(MessagingChat.tags, "") == "",
                func.coalesce(MessagingChat.notes, "") == "",
                func.coalesce(MessagingChat.followup_note, "") == "",
                func.coalesce(MessagingChat.budget_person, "") == "",
                ~MessagingChat.id.in_(
                    select(CrmContact.messaging_chat_id).where(
                        CrmContact.messaging_chat_id.is_not(None)
                    )
                ),
                ~MessagingChat.id.in_(chats_with_messages),
                or_(
                    MessagingChat.last_message_at < cutoff,
                    MessagingChat.last_message_at.is_(None)
                    & (func.coalesce(MessagingChat.updated_at, MessagingChat.created_at) < cutoff),
                ),
            )
        ).all()
    )
    removed_chats = 0
    if stale_chat_ids:
        db.execute(
            update(NotebookNote)
            .where(NotebookNote.messaging_chat_id.in_(stale_chat_ids))
            .values(messaging_chat_id=None, updated_at=now)
        )
        removed_chats = db.execute(
            delete(MessagingChat).where(MessagingChat.id.in_(stale_chat_ids))
        ).rowcount

    return {
        "messages": removed_messages,
        "media": removed_media,
        "chats": removed_chats,
    }
