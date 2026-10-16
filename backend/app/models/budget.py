import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime, utcnow

Money = Numeric(12, 2)


def _user_fk() -> Mapped[uuid.UUID]:
    return mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)


def _category_fk() -> Mapped[uuid.UUID | None]:
    return mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))


def _recurring_fk() -> Mapped[uuid.UUID | None]:
    return mapped_column(ForeignKey("recurring_items.id", ondelete="SET NULL"))


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = _user_fk()
    name: Mapped[str] = mapped_column(String(60))
    is_essential: Mapped[bool] = mapped_column(default=False)
    color: Mapped[str | None] = mapped_column(String(7))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class BudgetMonth(Base):
    """Marca que o mês já foi aberto, e por isso as contas e rendas fixas já foram lançadas nele."""

    __tablename__ = "budget_months"
    __table_args__ = (UniqueConstraint("user_id", "month"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = _user_fk()
    month: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class RecurringItem(Base):
    """Conta ou renda fixa, lançada automaticamente em cada mês aberto do período."""

    __tablename__ = "recurring_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = _user_fk()
    kind: Mapped[str] = mapped_column(String(10))  # "income" | "expense"
    description: Mapped[str] = mapped_column(String(120))
    amount: Mapped[Decimal] = mapped_column(Money)
    category_id: Mapped[uuid.UUID | None] = _category_fk()
    due_day: Mapped[int | None] = mapped_column(SmallInteger)
    start_month: Mapped[date] = mapped_column(Date)
    end_month: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Income(Base):
    __tablename__ = "incomes"
    __table_args__ = (
        Index("ix_incomes_user_id_month", "user_id", "month"),
        Index("ix_incomes_user_id_import_ref", "user_id", "import_ref"),
        UniqueConstraint("recurring_id", "month"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = _user_fk()
    month: Mapped[date] = mapped_column(Date)
    description: Mapped[str] = mapped_column(String(120))
    amount: Mapped[Decimal] = mapped_column(Money)
    recurring_id: Mapped[uuid.UUID | None] = _recurring_fk()
    # Identificador da origem (extrato bancário ou arquivo antigo), para não importar duas vezes.
    import_ref: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = (
        Index("ix_expenses_user_id_month", "user_id", "month"),
        Index("ix_expenses_user_id_import_ref", "user_id", "import_ref"),
        UniqueConstraint("recurring_id", "month"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = _user_fk()
    month: Mapped[date] = mapped_column(Date)
    description: Mapped[str] = mapped_column(String(120))
    amount: Mapped[Decimal] = mapped_column(Money)
    category_id: Mapped[uuid.UUID | None] = _category_fk()
    due_date: Mapped[date | None] = mapped_column(Date)
    paid: Mapped[bool] = mapped_column(default=False)
    paid_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    notes: Mapped[str | None] = mapped_column(String(500))

    # Compra parcelada: todas as parcelas compartilham o mesmo grupo.
    installment_group_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    installment_number: Mapped[int | None] = mapped_column(SmallInteger)
    installment_total: Mapped[int | None] = mapped_column(SmallInteger)

    recurring_id: Mapped[uuid.UUID | None] = _recurring_fk()
    import_ref: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = _user_fk()
    name: Mapped[str] = mapped_column(String(80))
    target_amount: Mapped[Decimal] = mapped_column(Money)
    current_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    target_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class Investment(Base):
    """Posição na carteira. O valor atual é informado pelo usuário."""

    __tablename__ = "investments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = _user_fk()
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(20))
    institution: Mapped[str | None] = mapped_column(String(80))
    invested_amount: Mapped[Decimal] = mapped_column(Money)
    current_value: Mapped[Decimal] = mapped_column(Money)
    # Conta como reserva de emergência no score financeiro.
    is_emergency_reserve: Mapped[bool] = mapped_column(default=False)
    notes: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
