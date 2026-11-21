"""Modelos SQLAlchemy do Dashboard & CRM integrados ao Hub (users, mensageria e orçamento)."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime, utcnow

Money = Numeric(12, 2)


def _user_fk() -> Mapped[uuid.UUID]:
    return mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)


class CrmPipeline(Base):
    """Funil comercial / operacional do CRM."""

    __tablename__ = "crm_pipelines"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = _user_fk()
    name: Mapped[str] = mapped_column(String(80))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class CrmStage(Base):
    """Etapa de um funil do CRM (coluna no Kanban / grupo no celular)."""

    __tablename__ = "crm_stages"
    __table_args__ = (Index("ix_crm_stages_pipeline_pos", "pipeline_id", "position"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    pipeline_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crm_pipelines.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(60))
    position: Mapped[int] = mapped_column(SmallInteger, default=0)
    is_won: Mapped[bool] = mapped_column(Boolean, default=False)
    is_lost: Mapped[bool] = mapped_column(Boolean, default=False)


class CrmContact(Base):
    """Contato unificado do CRM, com pontes limpas para Mensageria e Meu Orçamento."""

    __tablename__ = "crm_contacts"
    __table_args__ = (Index("ix_crm_contacts_user_name", "user_id", "name"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = _user_fk()
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(32))
    remote_jid: Mapped[str | None] = mapped_column(String(64), index=True)
    email: Mapped[str | None] = mapped_column(String(160))
    company: Mapped[str | None] = mapped_column(String(120))
    origin: Mapped[str | None] = mapped_column(String(60))
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    notes: Mapped[str | None] = mapped_column(Text)
    messaging_chat_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messaging_chats.id", ondelete="SET NULL"), index=True
    )
    budget_person: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class CrmDeal(Base):
    """Negócio / oportunidade no funil do CRM."""

    __tablename__ = "crm_deals"
    __table_args__ = (Index("ix_crm_deals_user_stage", "user_id", "stage_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = _user_fk()
    pipeline_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crm_pipelines.id", ondelete="CASCADE"), index=True
    )
    stage_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crm_stages.id", ondelete="CASCADE"), index=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crm_contacts.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(140))
    value: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    # "open" | "won" | "lost"
    status: Mapped[str] = mapped_column(String(12), default="open")
    expected_close_date: Mapped[date | None] = mapped_column(Date)
    budget_income_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("incomes.id", ondelete="SET NULL"), index=True
    )
    notes: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, default=0)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class CrmActivity(Base):
    """Registro de atividade / tarefa / interação vinculada a contato ou negócio."""

    __tablename__ = "crm_activities"
    __table_args__ = (Index("ix_crm_activities_user_created", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = _user_fk()
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crm_contacts.id", ondelete="CASCADE"), index=True
    )
    deal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crm_deals.id", ondelete="CASCADE"), index=True
    )
    # "note" | "task" | "call" | "message" | "budget"
    kind: Mapped[str] = mapped_column(String(16), default="note")
    body: Mapped[str] = mapped_column(Text)
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    done_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class DataSource(Base):
    """Fonte de dados unificada: nativa (CRM/Mensageria/Orçamento), PDF, CSV ou API externa."""

    __tablename__ = "data_sources"
    __table_args__ = (Index("ix_data_sources_user_kind", "user_id", "kind"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = _user_fk()
    name: Mapped[str] = mapped_column(String(120))
    # native_crm | native_crm_contacts | native_messaging | native_budget | csv | pdf | api
    kind: Mapped[str] = mapped_column(String(24))
    description: Mapped[str | None] = mapped_column(String(300))
    config_json: Mapped[dict] = mapped_column(JSON, default=dict)
    # Credenciais de API externa sempre cifradas em repouso (Fernet).
    credentials_encrypted: Mapped[str | None] = mapped_column(Text)
    # Esquema de colunas tipadas: [{"name": "...", "label": "...", "type": "currency|date|..."}]
    schema_json: Mapped[list] = mapped_column(JSON, default=list)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    last_synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_error: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class DataSnapshot(Base):
    """Foto tabular normalizada de uma DataSource para consultas rápidas nos dashboards."""

    __tablename__ = "data_snapshots"
    __table_args__ = (Index("ix_data_snapshots_source_created", "source_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("data_sources.id", ondelete="CASCADE"), index=True
    )
    rows_json: Mapped[list] = mapped_column(JSON, default=list)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    checksum: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class CrmDashboard(Base):
    """Painel personalizado composto por widgets configuráveis."""

    __tablename__ = "crm_dashboards"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = _user_fk()
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(240))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    # "all" | "7d" | "30d" | "90d" | "month" | "year"
    default_range: Mapped[str] = mapped_column(String(16), default="all")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class CrmWidget(Base):
    """Widget de um dashboard (KPI, barras, linha, rosca, funil ou tabela)."""

    __tablename__ = "crm_widgets"
    __table_args__ = (Index("ix_crm_widgets_dashboard_pos", "dashboard_id", "position"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    dashboard_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crm_dashboards.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("data_sources.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(100))
    # "kpi" | "bar" | "line" | "donut" | "funnel" | "table"
    widget_type: Mapped[str] = mapped_column(String(16))
    span: Mapped[int] = mapped_column(SmallInteger, default=1)
    position: Mapped[int] = mapped_column(SmallInteger, default=0)
    query_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
