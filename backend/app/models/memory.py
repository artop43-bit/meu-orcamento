"""Modelos da Fase D: Cofre de Documentos (`/cofre`) e Caderno (`/caderno`)."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime, utcnow


class VaultDocument(Base):
    """Documento ou comprovante permanente guardado no Cofre, com validade e texto indexado."""

    __tablename__ = "vault_documents"
    __table_args__ = (
        Index("ix_vault_documents_user_expires", "user_id", "expires_at"),
        Index("ix_vault_documents_user_category", "user_id", "category"),
        Index(
            "uq_vault_documents_user_messaging_media",
            "user_id",
            "messaging_media_id",
            unique=True,
            sqlite_where=text("messaging_media_id IS NOT NULL"),
            postgresql_where=text("messaging_media_id IS NOT NULL"),
        ),
        Index(
            "uq_vault_documents_user_proposal",
            "user_id",
            "proposal_id",
            unique=True,
            sqlite_where=text("proposal_id IS NOT NULL"),
            postgresql_where=text("proposal_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(160))
    # "warranty", "contract", "fiscal", "receipt", "certificate", "identity", "other"
    category: Mapped[str] = mapped_column(String(24), default="other")
    issuer: Mapped[str | None] = mapped_column(String(140))
    document_number: Mapped[str | None] = mapped_column(String(80))
    issue_date: Mapped[date | None] = mapped_column(Date)
    expires_at: Mapped[date | None] = mapped_column(Date)
    notify_days_before: Mapped[int] = mapped_column(Integer, default=30)
    notes: Mapped[str | None] = mapped_column(Text)

    file_name: Mapped[str] = mapped_column(String(160))
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    data: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    extracted_text: Mapped[str | None] = mapped_column(Text)
    ocr_used: Mapped[bool] = mapped_column(Boolean, default=False)

    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crm_contacts.id", ondelete="SET NULL"), index=True
    )
    deal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crm_deals.id", ondelete="SET NULL"), index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("work_projects.id", ondelete="SET NULL"), index=True
    )
    proposal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("commercial_documents.id", ondelete="SET NULL"), index=True
    )
    messaging_media_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messaging_media.id", ondelete="SET NULL"), index=True
    )

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class NotebookNote(Base):
    """Nota em Markdown do Caderno com links [[...]], pastas, modelos e vínculos do Hub."""

    __tablename__ = "notebook_notes"
    __table_args__ = (
        Index("ix_notebook_notes_user_pinned_upd", "user_id", "pinned", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(160))
    folder: Mapped[str] = mapped_column(String(60), default="Geral")
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    template_kind: Mapped[str] = mapped_column(String(24), default="blank")
    content: Mapped[str] = mapped_column(Text, default="")

    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crm_contacts.id", ondelete="SET NULL"), index=True
    )
    deal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crm_deals.id", ondelete="SET NULL"), index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("work_projects.id", ondelete="SET NULL"), index=True
    )
    messaging_chat_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messaging_chats.id", ondelete="SET NULL"), index=True
    )
    goal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("goals.id", ondelete="SET NULL"), index=True
    )
    vault_doc_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("vault_documents.id", ondelete="SET NULL"), index=True
    )

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
