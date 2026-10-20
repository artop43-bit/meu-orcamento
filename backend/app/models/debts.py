"""v1.0: financiamentos e empréstimos, outras dívidas e o patrimônio mês a mês."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, SmallInteger, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime, utcnow

Money = Numeric(12, 2)
# Taxa em % com 4 casas (ex.: 1.2500 = 1,25% ao mês).
Rate = Numeric(8, 4)


class Loan(Base):
    """Financiamento ou empréstimo com tabela de amortização (Price ou SAC).

    As parcelas a pagar viram despesas do mês (Expense.loan_id), como as compras parceladas.
    O saldo devedor de hoje sai da tabela, contando as parcelas já pagas.
    """

    __tablename__ = "loans"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # "home" | "vehicle" | "personal" | "payroll" | "overdraft" | "other"
    kind: Mapped[str] = mapped_column(String(10))
    name: Mapped[str] = mapped_column(String(80))
    institution: Mapped[str | None] = mapped_column(String(80))
    principal: Mapped[Decimal] = mapped_column(Money)
    rate: Mapped[Decimal] = mapped_column(Rate)
    rate_period: Mapped[str] = mapped_column(String(7))  # "monthly" | "yearly"
    system: Mapped[str] = mapped_column(String(5))  # "price" | "sac"
    installments: Mapped[int] = mapped_column(SmallInteger)
    first_due: Mapped[date] = mapped_column(Date)
    # Parcelas pagas antes de cadastrar no app (contrato em andamento).
    paid_before: Mapped[int] = mapped_column(SmallInteger, default=0)
    insurance_monthly: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    fee_monthly: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    # IOF somado ao valor financiado.
    iof: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL")
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("money_accounts.id", ondelete="SET NULL")
    )
    notes: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class OtherDebt(Base):
    """Dívida sem tabela (acordo, empréstimo de família...): saldo informado à mão."""

    __tablename__ = "other_debts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(80))
    balance: Mapped[Decimal] = mapped_column(Money)
    monthly_payment: Mapped[Decimal | None] = mapped_column(Money)
    notes: Mapped[str | None] = mapped_column(String(500))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class NetWorthSnapshot(Base):
    """Foto do patrimônio no mês (bens e investimentos, dívidas). Atualizada todo dia."""

    __tablename__ = "net_worth_snapshots"
    __table_args__ = (UniqueConstraint("user_id", "month"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    month: Mapped[date] = mapped_column(Date)
    assets: Mapped[Decimal] = mapped_column(Money)
    debts: Mapped[Decimal] = mapped_column(Money)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class SplitShare(Base):
    """Divisão de despesas: parte de uma despesa que outra pessoa deve (ou que a pessoa deve).

    direction "owes_me": a pessoa deve ao usuário (ex.: a parte dela num jantar que ele pagou);
    "i_owe": o usuário deve à pessoa. Acertar as contas marca as partes como quitadas.
    """

    __tablename__ = "split_shares"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    expense_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("expenses.id", ondelete="CASCADE"), index=True
    )
    person: Mapped[str] = mapped_column(String(60))
    description: Mapped[str] = mapped_column(String(120))
    amount: Mapped[Decimal] = mapped_column(Money)
    direction: Mapped[str] = mapped_column(String(7))  # "owes_me" | "i_owe"
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    settled_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
