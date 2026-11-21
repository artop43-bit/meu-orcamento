"""Modelos SQLAlchemy de Catálogo, Estoque, Pedidos e Documentos Comerciais em PDF."""

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
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime, utcnow

Money = Numeric(12, 2)
Qty = Numeric(12, 3)


def _user_fk() -> Mapped[uuid.UUID]:
    return mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)


class CatalogItem(Base):
    """Produto ou serviço comercializado com custo, preço de venda e saldo em estoque."""

    __tablename__ = "catalog_items"
    __table_args__ = (Index("ix_catalog_items_user_name", "user_id", "name"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = _user_fk()
    # "product" | "service"
    kind: Mapped[str] = mapped_column(String(16), default="product")
    sku: Mapped[str | None] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(140))
    unit: Mapped[str] = mapped_column(String(16), default="un")
    cost_price: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    sale_price: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    stock_qty: Mapped[Decimal] = mapped_column(Qty, default=Decimal("0"))
    min_stock: Mapped[Decimal] = mapped_column(Qty, default=Decimal("0"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class CommercialOrder(Base):
    """Pedido comercial com baixa de estoque e ponte para CRM e Meu Orçamento."""

    __tablename__ = "commercial_orders"
    __table_args__ = (
        Index("ix_commercial_orders_user_created", "user_id", "created_at"),
        UniqueConstraint("user_id", "number", name="uq_commercial_orders_user_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = _user_fk()
    number: Mapped[int] = mapped_column(Integer)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crm_contacts.id", ondelete="SET NULL"), index=True
    )
    customer_name: Mapped[str] = mapped_column(String(140))
    items_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    discount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    total_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    total_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    # "draft" | "confirmed" | "cancelled"
    status: Mapped[str] = mapped_column(String(16), default="draft")
    crm_deal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crm_deals.id", ondelete="SET NULL"), index=True
    )
    budget_income_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("incomes.id", ondelete="SET NULL"), index=True
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class CatalogMovement(Base):
    """Histórico auditável de entradas, saídas e ajustes de estoque."""

    __tablename__ = "catalog_movements"
    __table_args__ = (Index("ix_catalog_movements_item_created", "item_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = _user_fk()
    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalog_items.id", ondelete="CASCADE"), index=True
    )
    # "in" | "out" | "adjust"
    kind: Mapped[str] = mapped_column(String(12))
    qty: Mapped[Decimal] = mapped_column(Qty)
    reason: Mapped[str | None] = mapped_column(String(180))
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("commercial_orders.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class CommercialDocument(Base):
    """Proposta comercial, ordem de serviço, contrato ou recibo com exportação local em PDF."""

    __tablename__ = "commercial_documents"
    __table_args__ = (
        Index(
            "ix_commercial_documents_user_type_created",
            "user_id",
            "doc_type",
            "created_at",
        ),
        UniqueConstraint(
            "user_id",
            "doc_type",
            "number",
            name="uq_commercial_documents_user_type_number",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = _user_fk()
    # "proposal" | "service_order" | "contract" | "receipt"
    doc_type: Mapped[str] = mapped_column(String(20), default="proposal")
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(160))
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crm_contacts.id", ondelete="SET NULL"), index=True
    )
    crm_deal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crm_deals.id", ondelete="SET NULL"), index=True
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("commercial_orders.id", ondelete="SET NULL"), index=True
    )
    customer_name: Mapped[str] = mapped_column(String(140))
    customer_doc: Mapped[str | None] = mapped_column(String(40))
    customer_contact: Mapped[str | None] = mapped_column(String(120))
    items_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    discount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    total_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    valid_until: Mapped[date | None] = mapped_column(Date)
    terms_text: Mapped[str | None] = mapped_column(Text)
    # "draft" | "sent" | "approved" | "rejected" | "cancelled"
    status: Mapped[str] = mapped_column(String(16), default="draft")
    budget_income_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("incomes.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
