import json
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
    field_validator,
    model_validator,
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


# ---------------------------------------------------------------- consultor e tendências

Tone = Literal["praise", "info", "warning", "danger"]


class InsightMessage(BaseModel):
    tone: Tone
    title: str
    text: str
    category_id: uuid.UUID | None = None


class InsightsOut(BaseModel):
    month: str
    mood: Literal["great", "good", "attention", "concern", "empty"]
    headline: str
    summary: str
    savings_pct: float | None
    in_progress: bool
    messages: list[InsightMessage]
    alerts: list[InsightMessage]


class TrendPoint(BaseModel):
    month: date
    income: Decimal
    expenses: Decimal
    balance: Decimal
    savings_pct: float | None = None
    has_data: bool

    @field_serializer("month")
    def _serialize_month(self, value: date) -> str:
        return format_month(value)


class TrendCategory(BaseModel):
    category_id: uuid.UUID | None
    name: str
    color: str | None
    totals: list[Decimal]


class TrendAverages(BaseModel):
    income_3m: Decimal | None
    expenses_3m: Decimal | None
    balance_3m: Decimal | None
    income_6m: Decimal | None
    expenses_6m: Decimal | None
    balance_6m: Decimal | None


class Wealth(BaseModel):
    invested: Decimal
    current: Decimal
    return_value: Decimal
    reserve: Decimal


class GoalsTotal(BaseModel):
    count: int
    target: Decimal
    saved: Decimal


class TrendsOut(BaseModel):
    months: list[TrendPoint]
    categories: list[TrendCategory]
    averages: TrendAverages
    current: TrendPoint
    same_month_last_year: TrendPoint
    wealth: Wealth
    goals: GoalsTotal


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


# ---------------------------------------------------------------- monte sua análise

MonthKey = Annotated[str, StringConstraints(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]


class AnalysisConfig(BaseModel):
    metric: Literal["expenses", "income", "balance", "savings_rate", "investments"]
    period: Literal["3m", "6m", "12m", "24m", "custom"] = "6m"
    start: MonthKey | None = None
    end: MonthKey | None = None
    group: Literal["month", "month_category", "month_type", "category", "type", "kind"] = "month"
    categories: list[uuid.UUID] = Field(default_factory=list, max_length=30)
    compare: Literal["none", "previous", "last_year", "average"] = "none"
    chart: Literal["bar", "stacked", "line", "area", "donut", "hbar", "table"] = "bar"

    @model_validator(mode="after")
    def _check(self) -> "AnalysisConfig":
        if self.period == "custom" and (not self.start or not self.end):
            raise ValueError("Período personalizado precisa de início e fim.")
        if self.metric == "investments" and self.group != "kind":
            raise ValueError("Patrimônio é agrupado por tipo de investimento.")
        if self.metric != "investments" and self.group == "kind":
            raise ValueError("Agrupar por tipo de investimento só vale para patrimônio.")
        if self.metric not in ("expenses", "investments") and self.group != "month":
            raise ValueError("Renda, sobra e poupança só podem ser vistas por mês.")
        return self


class SeriesLabel(BaseModel):
    key: str
    label: str
    color: str | None = None


class SeriesLine(BaseModel):
    key: str
    name: str
    color: str | None
    values: list[float | None]


class SeriesCompare(BaseModel):
    name: str
    values: list[float | None]


class SeriesOut(BaseModel):
    labels: list[SeriesLabel]
    series: list[SeriesLine]
    compare: SeriesCompare | None
    unit: Literal["money", "percent"]
    total: float | None
    compare_total: float | None
    start: str
    end: str


SavedName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]


class SavedAnalysisIn(BaseModel):
    name: SavedName
    config: AnalysisConfig
    pinned: bool = False


class SavedAnalysisPatch(BaseModel):
    name: SavedName | None = None
    config: AnalysisConfig | None = None
    pinned: bool | None = None
    position: Annotated[int, Field(ge=0, le=100)] | None = None


class SavedAnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    config: AnalysisConfig
    pinned: bool
    position: int

    @field_validator("config", mode="before")
    @classmethod
    def _parse(cls, value: object) -> object:
        return json.loads(value) if isinstance(value, str) else value
