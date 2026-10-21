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
    Text,
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
    # Quanto o usuário quer gastar no máximo por mês nesta categoria (opcional).
    monthly_limit: Mapped[Decimal | None] = mapped_column(Money)
    # v1.3: a sobra do limite passa para o mês seguinte (a partir de carry_since).
    carry_over: Mapped[bool] = mapped_column(default=False, server_default="0")
    carry_since: Mapped[date | None] = mapped_column(Date)
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
    # Repete a cada N meses (1 = todo mês, 12 = anual).
    interval_months: Mapped[int] = mapped_column(SmallInteger, default=1)
    # Renda: "fixed" (salário, benefícios) ou "variable" (freelance, comissões).
    income_type: Mapped[str | None] = mapped_column(String(10))
    payment_method: Mapped[str | None] = mapped_column(String(12))
    notes: Mapped[str | None] = mapped_column(String(500))
    # v1.4: renda que entra numa conta (ex.: recarga do vale-refeição).
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("money_accounts.id", ondelete="SET NULL")
    )
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
    income_type: Mapped[str] = mapped_column(String(10), default="fixed")
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("money_accounts.id", ondelete="SET NULL"), index=True
    )
    # Dia previsto do recebimento (opcional).
    day: Mapped[int | None] = mapped_column(SmallInteger)
    # v1.4: faturamento do MEI (conta para o teto anual).
    mei: Mapped[bool] = mapped_column(default=False, server_default="0")
    notes: Mapped[str | None] = mapped_column(String(500))
    # Identificador da origem (extrato bancário ou arquivo antigo), para não importar duas vezes.
    import_ref: Mapped[str | None] = mapped_column(String(80))
    # Lote de importação (permite desfazer a importação inteira).
    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("import_batches.id", ondelete="SET NULL"), index=True
    )
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
    # "pix" | "debit" | "credit" | "boleto" | "cash"
    payment_method: Mapped[str | None] = mapped_column(String(12))
    # Compra no cartão: a conta fica no mês da fatura (vencimento) e guarda o dia da compra.
    card_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("credit_cards.id", ondelete="SET NULL"), index=True
    )
    purchase_date: Mapped[date | None] = mapped_column(Date)
    # Compra no débito com um cartão: só registra qual cartão foi usado (não entra em fatura).
    debit_card_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("credit_cards.id", ondelete="SET NULL")
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("money_accounts.id", ondelete="SET NULL"), index=True
    )
    # Veio do extrato e ainda não foi conferida (categoria, valor).
    needs_review: Mapped[bool] = mapped_column(default=False, server_default="0")
    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("import_batches.id", ondelete="SET NULL"), index=True
    )

    # Compra parcelada: todas as parcelas compartilham o mesmo grupo.
    installment_group_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    installment_number: Mapped[int | None] = mapped_column(SmallInteger)
    installment_total: Mapped[int | None] = mapped_column(SmallInteger)

    recurring_id: Mapped[uuid.UUID | None] = _recurring_fk()
    import_ref: Mapped[str | None] = mapped_column(String(80))
    # v1.0: parcela de um financiamento ou empréstimo.
    loan_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("loans.id", ondelete="SET NULL"), index=True
    )
    # v1.3: compra dividida em categorias (cada parte é uma conta com o seu valor).
    split_group_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = _user_fk()
    name: Mapped[str] = mapped_column(String(80))
    target_amount: Mapped[Decimal] = mapped_column(Money)
    current_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    target_date: Mapped[date | None] = mapped_column(Date)
    # Objetivo: tipo (reserva, bem, viagem, saúde...), motivação e plano de aporte mensal.
    kind: Mapped[str] = mapped_column(String(20), default="other", server_default="other")
    motivation: Mapped[str | None] = mapped_column(String(200))
    monthly_plan: Mapped[Decimal | None] = mapped_column(Money)
    # Meta principal: aparece em destaque no Orçamento.
    is_main: Mapped[bool] = mapped_column(default=False, server_default="0")
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class Challenge(Base):
    """Desafio de economia (v1.3): o progresso é calculado pelos lançamentos do período."""

    __tablename__ = "challenges"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = _user_fk()
    title: Mapped[str] = mapped_column(String(80))
    # "no_keyword" | "no_category" | "no_nonessential" | "max_category"
    kind: Mapped[str] = mapped_column(String(20))
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE")
    )
    keywords: Mapped[str | None] = mapped_column(String(200))
    max_amount: Mapped[Decimal | None] = mapped_column(Money)
    start_date: Mapped[date] = mapped_column(Date)
    days: Mapped[int] = mapped_column(SmallInteger)
    # Preenchidos quando o desafio termina: "won" ou "lost".
    result: Mapped[str | None] = mapped_column(String(6))
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class GoalContribution(Base):
    """Valor guardado (ou retirado) numa meta: base do ritmo e da projeção."""

    __tablename__ = "goal_contributions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    goal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("goals.id", ondelete="CASCADE"), index=True
    )
    amount: Mapped[Decimal] = mapped_column(Money)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class ImportBatch(Base):
    """Uma importação de arquivo: guarda o que entrou para poder desfazer de uma vez."""

    __tablename__ = "import_batches"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = _user_fk()
    filename: Mapped[str] = mapped_column(String(160))
    file_format: Mapped[str] = mapped_column(String(10))  # ofx | csv | xlsx | backup | legacy
    count: Mapped[int] = mapped_column(default=0)
    undone_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class ImportMapping(Base):
    """Mapeamento de colunas confirmado pelo usuário para um modelo de planilha (cabeçalho)."""

    __tablename__ = "import_mappings"
    __table_args__ = (UniqueConstraint("user_id", "signature"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = _user_fk()
    signature: Mapped[str] = mapped_column(String(64))
    mapping: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class Investment(Base):
    """Posição na carteira. O valor atual é informado pelo usuário."""

    __tablename__ = "investments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = _user_fk()
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(20))
    institution: Mapped[str | None] = mapped_column(String(80))
    # Código na bolsa (ex.: PETR4) e quantidade: com os dois, o valor atual vem da cotação.
    ticker: Mapped[str | None] = mapped_column(String(12))
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    invested_amount: Mapped[Decimal] = mapped_column(Money)
    current_value: Mapped[Decimal] = mapped_column(Money)
    # Conta como reserva de emergência no score financeiro.
    is_emergency_reserve: Mapped[bool] = mapped_column(default=False)
    notes: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class SavedAnalysis(Base):
    """Análise montada pelo usuário ("Minhas análises"); a configuração fica em JSON."""

    __tablename__ = "saved_analyses"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = _user_fk()
    name: Mapped[str] = mapped_column(String(60))
    config: Mapped[str] = mapped_column(Text)
    # Fixada no Resumo da Análise financeira.
    pinned: Mapped[bool] = mapped_column(default=False)
    position: Mapped[int] = mapped_column(SmallInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class PlannedExpense(Base):
    """Gasto previsto numa data futura (calendário): entra na projeção até virar lançamento."""

    __tablename__ = "planned_expenses"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = _user_fk()
    date: Mapped[date] = mapped_column(Date, index=True)
    description: Mapped[str] = mapped_column(String(120))
    amount: Mapped[Decimal] = mapped_column(Money)
    category_id: Mapped[uuid.UUID | None] = _category_fk()
    notes: Mapped[str | None] = mapped_column(String(500))
    # Preenchido quando o gasto acontece e vira uma conta de verdade.
    expense_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("expenses.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class WatchItem(Base):
    """Ativo que o usuário acompanha na seção Mercado."""

    __tablename__ = "watch_items"
    __table_args__ = (UniqueConstraint("user_id", "symbol"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = _user_fk()
    symbol: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class CreditCard(Base):
    """Cartão: no crédito, as compras caem na fatura certa pelo dia de fechamento; no débito,
    saem na hora da conta vinculada (sem fatura e sem usar limite)."""

    __tablename__ = "credit_cards"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = _user_fk()
    name: Mapped[str] = mapped_column(String(60))
    # Função do cartão: "credit", "debit" ou "both".
    kind: Mapped[str] = mapped_column(String(6), default="credit", server_default="credit")
    limit_amount: Mapped[Decimal | None] = mapped_column(Money)
    # Dia em que a fatura fecha (compras a partir dele vão para a próxima) e dia do vencimento.
    # Só existem quando o cartão tem crédito.
    closing_day: Mapped[int | None] = mapped_column(SmallInteger)
    due_day: Mapped[int | None] = mapped_column(SmallInteger)
    color: Mapped[str | None] = mapped_column(String(7))
    # Conta que paga a fatura (o saldo dela cai quando a fatura é paga).
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("money_accounts.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class CategoryRule(Base):
    """Regra automática: descrição que contém o texto vai para a categoria."""

    __tablename__ = "category_rules"
    __table_args__ = (UniqueConstraint("user_id", "pattern"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = _user_fk()
    # Texto já normalizado (minúsculas, sem acento).
    pattern: Mapped[str] = mapped_column(String(60))
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class MoneyAccount(Base):
    """Conta onde o dinheiro está: corrente, poupança, carteira..."""

    __tablename__ = "money_accounts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = _user_fk()
    name: Mapped[str] = mapped_column(String(60))
    kind: Mapped[str] = mapped_column(String(10))  # "checking" | "savings" | "wallet" | "other"
    # Saldo no dia em que a conta foi cadastrada (ponto de partida).
    initial_balance: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    color: Mapped[str | None] = mapped_column(String(7))
    archived: Mapped[bool] = mapped_column(default=False, server_default="0")
    # v1.4: vale-refeição/alimentação ("benefit"): só paga a categoria escolhida e recebe a
    # recarga mensal por uma renda fixa ligada à conta.
    benefit_category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL")
    )
    recurring_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("recurring_items.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Transfer(Base):
    """Dinheiro que muda de conta (não é receita nem despesa)."""

    __tablename__ = "transfers"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = _user_fk()
    from_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("money_accounts.id", ondelete="CASCADE")
    )
    to_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("money_accounts.id", ondelete="CASCADE")
    )
    amount: Mapped[Decimal] = mapped_column(Money)
    date: Mapped[date] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
