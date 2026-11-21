"""Modelos da solução de Mensageria (sessão do WhatsApp, conversas, mensagens e conector)."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime, utcnow


class MessagingSession(Base):
    """Número de WhatsApp da pessoa, ligado pelo conector interno (Baileys)."""

    __tablename__ = "messaging_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    # "disconnected" | "connecting" | "qr" | "ready" | "error"
    status: Mapped[str] = mapped_column(String(24), default="disconnected")
    # A pessoa pediu para manter conectado (o conector restaura essas sessões ao ligar).
    wanted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    phone: Mapped[str | None] = mapped_column(String(32))
    display_name: Mapped[str | None] = mapped_column(String(120))
    # JID do próprio número conectado (ex.: 5511999999999:12@s.whatsapp.net).
    wa_jid: Mapped[str | None] = mapped_column(String(64))
    qr_code: Mapped[str | None] = mapped_column(Text)
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_error: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class MessagingChat(Base):
    """Conversa individual (contato com número @s.whatsapp.net e/ou identificador @lid)."""

    __tablename__ = "messaging_chats"
    __table_args__ = (
        UniqueConstraint("user_id", "remote_jid", name="uq_messaging_chats_user_jid"),
        Index("ix_messaging_chats_user_last", "user_id", "last_message_at"),
        Index("ix_messaging_chats_user_lid", "user_id", "lid_jid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # Endereço usado para enviar: o número (@s.whatsapp.net) quando conhecido, senão o @lid.
    remote_jid: Mapped[str] = mapped_column(String(64))
    # Só os dígitos do número; vazio quando o WhatsApp esconde o número (contato só com LID).
    phone: Mapped[str | None] = mapped_column(String(32))
    lid_jid: Mapped[str | None] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(120))
    # Origem do nome: "fallback" < "push" < "contact" (agenda) < "manual" (editado no Hub).
    name_source: Mapped[str] = mapped_column(
        String(16), default="fallback", server_default="fallback"
    )
    avatar_data: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    avatar_mime: Mapped[str | None] = mapped_column(String(64))
    avatar_updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    notes: Mapped[str | None] = mapped_column(String(300))
    # Vínculo opcional com pessoa cadastrada em Divisões/Empréstimos do Meu Orçamento.
    budget_person: Mapped[str | None] = mapped_column(String(80))
    # Etiquetas de CRM separadas por vírgula (ex.: "Lead,Orçamento,Urgente").
    tags: Mapped[str | None] = mapped_column(String(240))
    # Status de atendimento: "open" (Em aberto) | "waiting" (Aguardando) | "resolved" (Resolvido).
    service_status: Mapped[str] = mapped_column(String(20), default="open", server_default="open")
    # Lembrete de retorno (follow-up) agendado na conversa.
    followup_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    followup_note: Mapped[str | None] = mapped_column(String(200))
    unread_count: Mapped[int] = mapped_column(Integer, default=0)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    last_message_preview: Mapped[str | None] = mapped_column(String(240))
    last_message_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class MessagingMedia(Base):
    """Arquivo de mídia (foto, áudio, vídeo, figurinha ou documento) guardado por até 7 dias."""

    __tablename__ = "messaging_media"
    __table_args__ = (Index("ix_messaging_media_user_created", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # "image" | "audio" | "video" | "document" | "sticker"
    kind: Mapped[str] = mapped_column(String(16))
    mime_type: Mapped[str] = mapped_column(String(128))
    file_name: Mapped[str | None] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(Integer)
    data: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class MessagingMessage(Base):
    """Mensagem enviada ou recebida dentro de uma conversa da Mensageria."""

    __tablename__ = "messaging_messages"
    __table_args__ = (
        Index("ix_messaging_messages_chat_created", "chat_id", "created_at"),
        Index("ix_messaging_messages_chat_updated", "chat_id", "updated_at"),
        Index("ix_messaging_messages_user_status", "user_id", "direction", "status"),
        # Deduplicação das mensagens do WhatsApp (NULL pode repetir).
        UniqueConstraint("user_id", "external_id", name="uq_messaging_messages_user_external"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    chat_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messaging_chats.id", ondelete="CASCADE"), index=True
    )
    # "in" (recebida) | "out" (enviada)
    direction: Mapped[str] = mapped_column(String(4))
    body: Mapped[str] = mapped_column(Text)
    # "chat" | "image" | "audio" | "video" | "document" | "sticker" | "other"
    message_type: Mapped[str] = mapped_column(String(16), default="chat")
    # "pending" | "sent" | "delivered" | "read" | "failed"
    status: Mapped[str] = mapped_column(String(16), default="sent")
    # Id da mensagem no WhatsApp (deduplicação, confirmações e citação).
    external_id: Mapped[str | None] = mapped_column(String(160))
    reply_to_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messaging_messages.id", ondelete="SET NULL"), index=True
    )
    media_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messaging_media.id", ondelete="SET NULL"), index=True
    )
    error_detail: Mapped[str | None] = mapped_column(String(300))
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # Reserva do item da fila pelo conector (evita envio duplo).
    claimed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    # Toda alteração muda esta data: a tela busca só o que mudou desde a última consulta.
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class MessagingAuthKey(Base):
    """Credenciais do WhatsApp de cada sessão (lidas e gravadas direto pelo conector)."""

    __tablename__ = "messaging_auth_keys"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messaging_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    # As credenciais principais ficam em category="creds" e key_id="".
    category: Mapped[str] = mapped_column(String(48), primary_key=True)
    key_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, server_default=func.now()
    )


class MessagingConnectorKV(Base):
    """Valores soltos do conector (ex.: wa_version, a última versão do WhatsApp Web que deu)."""

    __tablename__ = "messaging_connector_kv"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, server_default=func.now()
    )


class MessagingQuickReply(Base):
    """Atalhos de resposta rápida (/pix, /cobranca, /boasvindas...) com variáveis dinâmicas."""

    __tablename__ = "messaging_quick_replies"
    __table_args__ = (
        UniqueConstraint("user_id", "shortcut", name="uq_messaging_quick_replies_user_shortcut"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    shortcut: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(80))
    body: Mapped[str] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
