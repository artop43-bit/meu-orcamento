"""Modelos SQLAlchemy de Projetos & Tarefas e Agenda & Compromissos integrados ao Hub."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime, utcnow

Money = Numeric(12, 2)


def _user_fk() -> Mapped[uuid.UUID]:
    return mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)


class WorkProject(Base):
    """Projeto de entrega com Kanban, horas trabalhadas e rentabilidade ligada ao Orçamento."""

    __tablename__ = "work_projects"
    __table_args__ = (
        Index("ix_work_projects_user_status", "user_id", "status"),
        Index(
            "uq_work_projects_user_deal",
            "user_id",
            "crm_deal_id",
            unique=True,
            sqlite_where=text("crm_deal_id IS NOT NULL"),
            postgresql_where=text("crm_deal_id IS NOT NULL"),
        ),
        Index(
            "uq_work_projects_user_proposal",
            "user_id",
            "proposal_id",
            unique=True,
            sqlite_where=text("proposal_id IS NOT NULL"),
            postgresql_where=text("proposal_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = _user_fk()
    name: Mapped[str] = mapped_column(String(140))
    description: Mapped[str | None] = mapped_column(Text)
    # "planning" | "active" | "review" | "done" | "paused"
    status: Mapped[str] = mapped_column(String(20), default="planning")
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crm_contacts.id", ondelete="SET NULL"), index=True
    )
    crm_deal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crm_deals.id", ondelete="SET NULL"), index=True
    )
    proposal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("commercial_documents.id", ondelete="SET NULL"), index=True
    )
    budget_project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    budget_value: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    hourly_rate: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    start_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class ProjectTask(Base):
    """Tarefa do projeto (Kanban, checklists e prazo sincronizado na Agenda)."""

    __tablename__ = "project_tasks"
    __table_args__ = (Index("ix_project_tasks_project_status", "project_id", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = _user_fk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("work_projects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text)
    # "todo" | "doing" | "done"
    status: Mapped[str] = mapped_column(String(16), default="todo")
    # "low" | "medium" | "high" | "urgent"
    priority: Mapped[str] = mapped_column(String(12), default="medium")
    due_date: Mapped[date | None] = mapped_column(Date, index=True)
    checklist_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    position: Mapped[int] = mapped_column(Integer, default=0)
    source_chat_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messaging_chats.id", ondelete="SET NULL"), index=True
    )
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messaging_messages.id", ondelete="SET NULL"), index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class ProjectTimeEntry(Base):
    """Apontamento de horas dedicadas ao projeto/tarefa para calcular o ganho real por hora."""

    __tablename__ = "project_time_entries"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = _user_fk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("work_projects.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_tasks.id", ondelete="SET NULL"), index=True
    )
    hours: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    entry_date: Mapped[date] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(String(240))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AgendaEvent(Base):
    """Compromisso próprio da Agenda vinculado a clientes, projetos e WhatsApp."""

    __tablename__ = "agenda_events"
    __table_args__ = (Index("ix_agenda_events_user_start", "user_id", "start_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = _user_fk()
    title: Mapped[str] = mapped_column(String(160))
    # "meeting" | "delivery" | "visit" | "reminder" | "personal"
    kind: Mapped[str] = mapped_column(String(20), default="meeting")
    start_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    end_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    all_day: Mapped[bool] = mapped_column(Boolean, default=False)
    location: Mapped[str | None] = mapped_column(String(180))
    # "scheduled" | "confirmed" | "done" | "cancelled"
    status: Mapped[str] = mapped_column(String(16), default="scheduled")
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crm_contacts.id", ondelete="SET NULL"), index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("work_projects.id", ondelete="SET NULL"), index=True
    )
    messaging_chat_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messaging_chats.id", ondelete="SET NULL"), index=True
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
