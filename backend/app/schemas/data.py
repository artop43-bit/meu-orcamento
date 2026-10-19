import uuid
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.schemas.budget import Description, Money, MonthStr, SafeDate

MAX_FILE_CHARS = 5_000_000
NonNegative = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]

# ---------------------------------------------------------------- app antigo


class LegacyPreviewIn(BaseModel):
    month: MonthStr
    # Conteúdo do .json do app antigo, já lido pelo navegador.
    data: dict[str, Any]


class LegacyIncome(BaseModel):
    description: Description
    amount: Money
    recurring: bool = True


class LegacyExpense(BaseModel):
    description: Description
    amount: Money
    category_name: Annotated[str, StringConstraints(max_length=60)] | None = None
    due_day: Annotated[int, Field(ge=1, le=31)] | None = None
    paid: bool = False
    notes: Annotated[str, StringConstraints(max_length=500)] | None = None
    installment_current: Annotated[int, Field(ge=1, le=120)] | None = None
    installment_total: Annotated[int, Field(ge=2, le=120)] | None = None
    recurring: bool = False


class LegacyGoal(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    target_amount: Money
    current_amount: NonNegative = Decimal("0")


class LegacyHistory(BaseModel):
    month: MonthStr
    income: NonNegative
    expenses: NonNegative


class LegacyImport(BaseModel):
    month: MonthStr
    incomes: Annotated[list[LegacyIncome], Field(max_length=200)] = []
    expenses: Annotated[list[LegacyExpense], Field(max_length=500)] = []
    goals: Annotated[list[LegacyGoal], Field(max_length=100)] = []
    history: Annotated[list[LegacyHistory], Field(max_length=240)] = []
    reserve: Money | None = None


class LegacyPreviewOut(LegacyImport):
    already_imported: bool


class LegacyResult(BaseModel):
    incomes: int
    expenses: int
    goals: int
    history_months: int
    investments: int


# ---------------------------------------------------------------- extratos


class StatementPreviewIn(BaseModel):
    filename: Annotated[str, StringConstraints(max_length=200)]
    content: Annotated[str, StringConstraints(max_length=MAX_FILE_CHARS)]
    # Faturas de cartão costumam trazer compras como valores positivos.
    invert: bool = False


Ref = Annotated[str, Field(pattern=r"^stmt:[0-9a-f]{40}$")]


class StatementTransaction(BaseModel):
    ref: Ref
    date: SafeDate
    description: Description
    amount: Money
    kind: Literal["income", "expense"]
    category_id: uuid.UUID | None = None


class StatementPreviewItem(StatementTransaction):
    duplicate: bool
    # Pagamento da fatura do cartão: as compras já estão no app, então vem desmarcado.
    card_payment: bool = False


class StatementPreviewOut(BaseModel):
    format: Literal["ofx", "csv"]
    transactions: list[StatementPreviewItem]


class StatementImportIn(BaseModel):
    transactions: Annotated[list[StatementTransaction], Field(min_length=1, max_length=2000)]


class StatementResult(BaseModel):
    created: int
    skipped: int
