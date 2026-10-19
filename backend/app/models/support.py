"""Solicitações (conversas com a administração), arquivos de imagem e perfil."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, LargeBinary, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime, utcnow


class StoredFile(Base):
    """Imagem enviada por um usuário (anexo de solicitação, foto ou banner do perfil).

    Fica no próprio banco: entra no backup diário junto com o resto e some com a conta.
    Só o dono e a administração conseguem abrir (ver app/services/files.py).
    """

    __tablename__ = "stored_files"
    __table_args__ = (Index("ix_stored_files_owner_purpose", "owner_id", "purpose"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # "attachment" (anexo de mensagem), "avatar" ou "banner".
    purpose: Mapped[str] = mapped_column(String(12))
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("support_messages.id", ondelete="CASCADE"), index=True
    )
    content_type: Mapped[str] = mapped_column(String(20))
    size: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class SupportThread(Base):
    """Uma solicitação: sugestão, problema ou outro assunto, com a conversa inteira."""

    __tablename__ = "support_threads"
    __table_args__ = (Index("ix_support_threads_last_message_at", "last_message_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(10))  # "idea" | "bug" | "other"
    # "open" (aguardando a administração), "answered" (respondida) ou "resolved".
    status: Mapped[str] = mapped_column(String(10), default="open")
    # Quem ainda não leu a última mensagem do outro lado.
    user_unread: Mapped[bool] = mapped_column(default=False)
    admin_unread: Mapped[bool] = mapped_column(default=True)
    page: Mapped[str | None] = mapped_column(String(200))
    app_version: Mapped[str | None] = mapped_column(String(20))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_message_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class SupportMessage(Base):
    __tablename__ = "support_messages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    thread_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("support_threads.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    from_admin: Mapped[bool] = mapped_column(default=False)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
