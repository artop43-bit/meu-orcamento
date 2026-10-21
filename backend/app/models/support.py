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
    # "attachment" (anexo de mensagem), "avatar", "banner", "receipt" (comprovante) ou "goal".
    purpose: Mapped[str] = mapped_column(String(12))
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("support_messages.id", ondelete="CASCADE"), index=True
    )
    # Comprovante de uma despesa ou imagem de uma meta.
    expense_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("expenses.id", ondelete="CASCADE"), index=True
    )
    goal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("goals.id", ondelete="CASCADE"), index=True
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
    # v1.1: número fixo e crescente (#1, #2...), para tratar as solicitações como tarefas.
    number: Mapped[int] = mapped_column(Integer, unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(10))  # "idea" | "bug" | "other"
    # "open" (aberta), "in_progress" (em andamento), "planned" (planejada), "answered"
    # (respondida), "resolved" (resolvida) ou "declined" (recusada).
    status: Mapped[str] = mapped_column(String(12), default="open")
    # Nota do status (ex.: "entra na versão 1.2") e versão planejada.
    status_note: Mapped[str | None] = mapped_column(String(200))
    planned_version: Mapped[str | None] = mapped_column(String(20))
    # v1.1: conversa que começou como resposta a um recado da administração.
    announcement_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("announcements.id", ondelete="SET NULL"), index=True
    )
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


class Announcement(Base):
    """Recado da administração para todos os usuários (v0.9)."""

    __tablename__ = "announcements"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text)
    # Fica fixado no topo da caixa de mensagens e sempre gera e-mail.
    important: Mapped[bool] = mapped_column(default=False)
    # Também para quem está aguardando a liberação do acesso.
    include_pending: Mapped[bool] = mapped_column(default=False)
    recipients: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class InboxItem(Base):
    """Mensagem na caixa do usuário: resposta a uma solicitação ou recado da administração."""

    __tablename__ = "inbox_items"
    __table_args__ = (Index("ix_inbox_items_user_created", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(12))  # "reply" | "announcement"
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(Text)
    important: Mapped[bool] = mapped_column(default=False)
    thread_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("support_threads.id", ondelete="CASCADE"), index=True
    )
    announcement_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("announcements.id", ondelete="CASCADE"), index=True
    )
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class ErrorEvent(Base):
    """Erro das telas ou do servidor, agrupado pela impressão digital (tipo, mensagem e tela)."""

    __tablename__ = "error_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    fingerprint: Mapped[str] = mapped_column(String(32), unique=True)
    source: Mapped[str] = mapped_column(String(6))  # "web" | "api"
    name: Mapped[str] = mapped_column(String(80))
    message: Mapped[str] = mapped_column(String(300))
    path: Mapped[str | None] = mapped_column(String(200))
    detail: Mapped[str | None] = mapped_column(Text)
    user_agent: Mapped[str | None] = mapped_column(String(200))
    release: Mapped[str | None] = mapped_column(String(20))
    count: Mapped[int] = mapped_column(default=0)
    first_seen: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
