import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_serializer

from app.core.months import format_month

Money = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
CategoryName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
GoalName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Notes = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
Color = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]
MonthStr = Annotated[str, Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]
DueDay = Annotated[int, Field(ge=1, le=31)]
# Para campos chamados "date" (o nome do campo esconderia o tipo dentro da classe).
Day = date
IncomeType = Literal["fixed", "variable"]
PaymentMethod = Literal["pix", "debit", "credit", "boleto", "cash"]
# Repete a cada N meses: mensal, bimestral, trimestral, semestral ou anual.
Interval = Literal[1, 2, 3, 6, 12]


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class _MonthOut(_Out):
    month: date

    @field_serializer("month")
    def _serialize_month(self, value: date) -> str:
        return format_month(value)


# ---------------------------------------------------------------- categorias


class CategoryIn(BaseModel):
    name: CategoryName
    is_essential: bool = False
    color: Color | None = None
    monthly_limit: Money | None = None


class CategoryPatch(BaseModel):
    name: CategoryName | None = None
    is_essential: bool | None = None
    color: Color | None = None
    monthly_limit: Money | None = None


class CategoryOut(_Out):
    id: uuid.UUID
    name: str
    is_essential: bool
    color: str | None
    monthly_limit: Decimal | None


# ---------------------------------------------------------------- rendas


class IncomeIn(BaseModel):
    description: Description
    amount: Money
    income_type: IncomeType = "fixed"
    day: DueDay | None = None
    notes: Notes | None = None
    # once = só este mês; monthly = todo mês (sem fim); period = de este mês até `until_month`.
    repeat: Literal["once", "monthly", "period"] = "once"
    until_month: MonthStr | None = None


class IncomePatch(BaseModel):
    description: Description | None = None
    amount: Money | None = None
    income_type: IncomeType | None = None
    day: DueDay | None = None
    notes: Notes | None = None


class IncomeOut(_MonthOut):
    id: uuid.UUID
    description: str
    amount: Decimal
    income_type: str
    day: int | None
    notes: str | None
    recurring_id: uuid.UUID | None


# ---------------------------------------------------------------- contas


class ExpenseIn(BaseModel):
    description: Description
    amount: Money
    category_id: uuid.UUID | None = None
    due_date: date | None = None
    notes: Notes | None = None
    # Já paga ao lançar (compras do dia a dia). Na parcelada, vale para a 1ª parcela.
    paid: bool = False
    payment_method: PaymentMethod | None = None
    # Compra parcelada: cria uma conta por mês, começando no mês informado.
    installments: Annotated[int, Field(ge=2, le=120)] | None = None
    # Na parcelada, `amount` é o valor de cada parcela ("parcel") ou o total da compra ("total").
    amount_mode: Literal["parcel", "total"] = "parcel"
    # Conta que se repete: cria uma fixa a partir deste mês, a cada `interval_months`.
    repeat: bool = False
    interval_months: Interval = 1
    until_month: MonthStr | None = None
    # Compra no cartão: o mês e o vencimento vêm da fatura em que a compra cai.
    card_id: uuid.UUID | None = None
    purchase_date: Day | None = None


class ExpensePatch(BaseModel):
    description: Description | None = None
    amount: Money | None = None
    category_id: uuid.UUID | None = None
    due_date: date | None = None
    paid: bool | None = None
    notes: Notes | None = None
    payment_method: PaymentMethod | None = None


class ExpenseOut(_MonthOut):
    id: uuid.UUID
    description: str
    amount: Decimal
    category_id: uuid.UUID | None
    due_date: date | None
    paid: bool
    paid_at: datetime | None
    notes: str | None
    payment_method: str | None
    card_id: uuid.UUID | None
    purchase_date: date | None
    installment_group_id: uuid.UUID | None
    installment_number: int | None
    installment_total: int | None
    recurring_id: uuid.UUID | None


DeleteScope = Literal["one", "following"]
EditScope = Literal["one", "following"]


# ---------------------------------------------------------------- fixas (recorrentes)


class RecurringIn(BaseModel):
    kind: Literal["income", "expense"]
    description: Description
    amount: Money
    category_id: uuid.UUID | None = None
    due_day: DueDay | None = None
    start_month: MonthStr
    end_month: MonthStr | None = None
    interval_months: Interval = 1
    income_type: IncomeType | None = None
    payment_method: PaymentMethod | None = None
    notes: Notes | None = None


class RecurringPatch(BaseModel):
    description: Description | None = None
    amount: Money | None = None
    category_id: uuid.UUID | None = None
    due_day: DueDay | None = None
    end_month: MonthStr | None = None
    interval_months: Interval | None = None
    income_type: IncomeType | None = None
    payment_method: PaymentMethod | None = None
    notes: Notes | None = None


class RecurringOut(_Out):
    id: uuid.UUID
    kind: str
    description: str
    amount: Decimal
    category_id: uuid.UUID | None
    due_day: int | None
    start_month: date
    end_month: date | None
    interval_months: int
    income_type: str | None
    payment_method: str | None
    notes: str | None

    @field_serializer("start_month", "end_month")
    def _serialize_months(self, value: date | None) -> str | None:
        return format_month(value) if value else None


# ---------------------------------------------------------------- mês


class CategoryTotal(BaseModel):
    category_id: uuid.UUID | None
    name: str
    is_essential: bool
    total: Decimal
    limit: Decimal | None = None
    limit_pct: float | None = None


class MonthSummary(BaseModel):
    income_total: Decimal
    expense_total: Decimal
    paid_total: Decimal
    pending_total: Decimal
    balance: Decimal
    # Percentual da renda comprometido com contas (None se não há renda).
    committed_pct: float | None
    essential_total: Decimal
    non_essential_total: Decimal
    by_category: list[CategoryTotal]


class MonthOut(BaseModel):
    month: str
    incomes: list[IncomeOut]
    expenses: list[ExpenseOut]
    summary: MonthSummary


class HistoryPoint(BaseModel):
    month: str
    income: Decimal
    expenses: Decimal
    paid: Decimal
    balance: Decimal
    committed_pct: float | None
    has_data: bool


# ---------------------------------------------------------------- metas


class GoalIn(BaseModel):
    name: GoalName
    target_amount: Money
    current_amount: Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)] = Decimal("0")
    target_date: date | None = None


class GoalPatch(BaseModel):
    name: GoalName | None = None
    target_amount: Money | None = None
    target_date: date | None = None


class ContributionIn(BaseModel):
    # Negativo para retirar dinheiro da meta.
    amount: Annotated[Decimal, Field(max_digits=12, decimal_places=2)]


class GoalOut(_Out):
    id: uuid.UUID
    name: str
    target_amount: Decimal
    current_amount: Decimal
    target_date: date | None
    progress_pct: float


# ---------------------------------------------------------------- planejados e calendário


class PlannedIn(BaseModel):
    date: Day
    description: Description
    amount: Money
    category_id: uuid.UUID | None = None
    notes: Notes | None = None


class PlannedPatch(BaseModel):
    date: Day | None = None
    description: Description | None = None
    amount: Money | None = None
    category_id: uuid.UUID | None = None
    notes: Notes | None = None


class PlannedOut(_Out):
    id: uuid.UUID
    date: Day
    description: str
    amount: Decimal
    category_id: uuid.UUID | None
    notes: str | None
    expense_id: uuid.UUID | None


class ConfirmPlannedIn(BaseModel):
    paid: bool = False


class CalendarEvent(BaseModel):
    id: uuid.UUID
    date: Day | None
    # expense | installment | recurring | income | planned
    kind: str
    description: str
    amount: Decimal
    paid: bool | None
    category_id: uuid.UUID | None = None
    category: str | None = None
    color: str | None = None
    installment_number: int | None = None
    installment_total: int | None = None
    income_type: str | None = None
    expense_id: uuid.UUID | None = None
    notes: str | None = None


class CalendarOut(BaseModel):
    month: str
    events: list[CalendarEvent]


# ---------------------------------------------------------------- sugestões


class CategorySuggestion(BaseModel):
    category_id: uuid.UUID
    name: str
    # history = aprendido com os seus lançamentos; keywords = palavra conhecida
    source: Literal["rule", "history", "keywords"]


class DescriptionSuggestion(BaseModel):
    description: str
    amount: Decimal
    category_id: uuid.UUID | None
    payment_method: str | None
    count: int


# ---------------------------------------------------------------- v0.6


class BulkIn(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    action: Literal["pay", "unpay", "delete", "category"]
    category_id: uuid.UUID | None = None


CardName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]


class CardIn(BaseModel):
    name: CardName
    limit_amount: Money | None = None
    closing_day: DueDay
    due_day: DueDay
    color: Color | None = None


class CardPatch(BaseModel):
    name: CardName | None = None
    limit_amount: Money | None = None
    closing_day: DueDay | None = None
    due_day: DueDay | None = None
    color: Color | None = None


class CardOut(_Out):
    id: uuid.UUID
    name: str
    limit_amount: Decimal | None
    closing_day: int
    due_day: int
    color: str | None


class InvoiceOut(_MonthOut):
    closing_date: date
    due_date: date
    total: Decimal
    paid_total: Decimal
    count: int
    status: Literal["open", "closed", "paid", "overdue"]


class CardSummary(BaseModel):
    card: CardOut
    used: Decimal
    available: Decimal | None
    used_pct: float | None
    best_day: int
    open_invoice: InvoiceOut
    closed_invoice: InvoiceOut | None


class PayInvoiceIn(BaseModel):
    paid: bool = True


class RuleIn(BaseModel):
    pattern: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=60)]
    category_id: uuid.UUID


class RuleOut(_Out):
    id: uuid.UUID
    pattern: str
    category_id: uuid.UUID


class DayPoint(BaseModel):
    date: date
    balance: Decimal
    change: Decimal


class CanSpend(BaseModel):
    today: Decimal
    rest_of_month: Decimal
    days_left: int


class LowestPoint(BaseModel):
    date: date
    balance: Decimal


class DailyOut(_MonthOut):
    days: list[DayPoint]
    end_balance: Decimal
    lowest: LowestPoint | None
    first_negative: date | None
    planned_total: Decimal
    can_spend: CanSpend | None


class FixedCost(BaseModel):
    id: uuid.UUID
    description: str
    amount: Decimal
    interval_months: int
    category_id: uuid.UUID | None
    monthly: Decimal
    yearly: Decimal


class SubscriptionCandidate(BaseModel):
    description: str
    amount: Decimal
    category_id: uuid.UUID | None
    due_day: int | None
    months: list[str]
    yearly: Decimal


class SubscriptionsOut(BaseModel):
    fixed: list[FixedCost]
    candidates: list[SubscriptionCandidate]
    monthly_total: Decimal
    yearly_total: Decimal


class PromoteIn(BaseModel):
    description: Description
    amount: Money
    category_id: uuid.UUID | None = None
    due_day: DueDay | None = None
