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


class IncomePatch(BaseModel):
    description: Description | None = None
    amount: Money | None = None


class IncomeOut(_MonthOut):
    id: uuid.UUID
    description: str
    amount: Decimal
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
    # Compra parcelada: cria uma conta por mês, começando no mês informado.
    installments: Annotated[int, Field(ge=2, le=120)] | None = None


class ExpensePatch(BaseModel):
    description: Description | None = None
    amount: Money | None = None
    category_id: uuid.UUID | None = None
    due_date: date | None = None
    paid: bool | None = None
    notes: Notes | None = None


class ExpenseOut(_MonthOut):
    id: uuid.UUID
    description: str
    amount: Decimal
    category_id: uuid.UUID | None
    due_date: date | None
    paid: bool
    paid_at: datetime | None
    notes: str | None
    installment_group_id: uuid.UUID | None
    installment_number: int | None
    installment_total: int | None
    recurring_id: uuid.UUID | None


DeleteScope = Literal["one", "following"]


# ---------------------------------------------------------------- fixas (recorrentes)


class RecurringIn(BaseModel):
    kind: Literal["income", "expense"]
    description: Description
    amount: Money
    category_id: uuid.UUID | None = None
    due_day: DueDay | None = None
    start_month: MonthStr
    end_month: MonthStr | None = None


class RecurringPatch(BaseModel):
    description: Description | None = None
    amount: Money | None = None
    category_id: uuid.UUID | None = None
    due_day: DueDay | None = None
    end_month: MonthStr | None = None


class RecurringOut(_Out):
    id: uuid.UUID
    kind: str
    description: str
    amount: Decimal
    category_id: uuid.UUID | None
    due_day: int | None
    start_month: date
    end_month: date | None

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
