import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    computed_field,
    field_serializer,
)

from app.core.months import format_month

# ---------------------------------------------------------------- análises


class ScoreComponent(BaseModel):
    key: str
    label: str
    points: float
    max: int
    detail: str


class ScoreOut(BaseModel):
    score: int | None
    label: str
    components: list[ScoreComponent]
    tips: list[str]
    reserve_total: Decimal
    reserve_months: float | None


class RuleOut(BaseModel):
    income: Decimal
    needs: Decimal
    wants: Decimal
    savings: Decimal
    deficit: Decimal
    needs_pct: float | None
    wants_pct: float | None
    savings_pct: float | None
    needs_ok: bool
    wants_ok: bool
    savings_ok: bool


class OverviewOut(BaseModel):
    month: str
    score: ScoreOut
    rule: RuleOut


class CompareTotals(BaseModel):
    a: Decimal
    b: Decimal
    delta: Decimal


class CompareCategory(BaseModel):
    category_id: uuid.UUID | None
    name: str
    a: Decimal
    b: Decimal
    delta: Decimal
    delta_pct: float | None


class CompareOut(BaseModel):
    month_a: str
    month_b: str
    income: CompareTotals
    expenses: CompareTotals
    balance: CompareTotals
    categories: list[CompareCategory]


class ProjectionPoint(BaseModel):
    month: date
    income: Decimal
    expenses: Decimal
    non_essential: Decimal
    balance: Decimal
    cumulative: Decimal

    @field_serializer("month")
    def _serialize_month(self, value: date) -> str:
        return format_month(value)


# ---------------------------------------------------------------- investimentos

InvestmentKind = Literal[
    "poupanca", "renda_fixa", "tesouro", "fundos", "acoes", "fiis", "cripto", "previdencia", "outro"
]
NonNegativeMoney = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Institution = Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)]
Notes = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class InvestmentIn(BaseModel):
    name: Name
    kind: InvestmentKind
    institution: Institution | None = None
    invested_amount: NonNegativeMoney
    current_value: NonNegativeMoney
    is_emergency_reserve: bool = False
    notes: Notes | None = None


class InvestmentPatch(BaseModel):
    name: Name | None = None
    kind: InvestmentKind | None = None
    institution: Institution | None = None
    invested_amount: NonNegativeMoney | None = None
    current_value: NonNegativeMoney | None = None
    is_emergency_reserve: bool | None = None
    notes: Notes | None = None


class InvestmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    kind: str
    institution: str | None
    invested_amount: Decimal
    current_value: Decimal
    is_emergency_reserve: bool
    notes: str | None
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def return_amount(self) -> Decimal:
        return self.current_value - self.invested_amount

    @computed_field  # type: ignore[prop-decorator]
    @property
    def return_pct(self) -> float | None:
        if self.invested_amount <= 0:
            return None
        return round(float(self.return_amount / self.invested_amount * 100), 2)


class Indicator(BaseModel):
    value: float
    date: str


class IndicatorsOut(BaseModel):
    available: bool
    selic: Indicator | None
    cdi: Indicator | None
    ipca_12m: Indicator | None
    fetched_at: datetime
