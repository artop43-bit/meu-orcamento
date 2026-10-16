import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.budget import _changes
from app.api.deps import CurrentUser, DbSession
from app.core.months import current_month, format_month, parse_month
from app.schemas.analysis import (
    CompareOut,
    IndicatorsOut,
    InsightsOut,
    InvestmentIn,
    InvestmentOut,
    InvestmentPatch,
    OverviewOut,
    ProjectionPoint,
    RuleOut,
    ScoreOut,
    TrendsOut,
)
from app.services import analysis, indicators, insights, investments

router = APIRouter(tags=["análises"])


# ---------------------------------------------------------------- análises


@router.get("/analysis/overview")
def overview(user: CurrentUser, db: DbSession, month: str | None = None) -> OverviewOut:
    """Score financeiro e regra 50/30/20 do mês (padrão: mês atual)."""
    target = parse_month(month) if month else current_month()
    return OverviewOut(
        month=format_month(target),
        score=ScoreOut.model_validate(analysis.score(db, user, target)),
        rule=RuleOut.model_validate(analysis.rule_50_30_20(db, user, target)),
    )


@router.get("/analysis/compare")
def compare(user: CurrentUser, db: DbSession, a: str, b: str) -> CompareOut:
    month_a, month_b = parse_month(a), parse_month(b)
    data = analysis.compare(db, user, month_a, month_b)
    return CompareOut.model_validate(
        {**data, "month_a": format_month(month_a), "month_b": format_month(month_b)}
    )


@router.get("/analysis/projection")
def projection(
    user: CurrentUser,
    db: DbSession,
    start: str | None = None,
    months: Annotated[int, Query(ge=1, le=36)] = 12,
) -> list[ProjectionPoint]:
    first = parse_month(start) if start else current_month()
    return [ProjectionPoint.model_validate(p) for p in analysis.projection(db, user, first, months)]


@router.get("/analysis/insights")
def get_insights(user: CurrentUser, db: DbSession, month: str | None = None) -> InsightsOut:
    """Leitura do mês pelo "consultor": resumo, elogios, alertas e próximos passos."""
    target = parse_month(month) if month else current_month()
    return InsightsOut.model_validate(insights.consultant(db, user, target))


@router.get("/analysis/trends")
def get_trends(
    user: CurrentUser,
    db: DbSession,
    until: str | None = None,
    months: Annotated[int, Query(ge=3, le=24)] = 12,
) -> TrendsOut:
    """Evolução de renda, gastos e categorias, médias e comparação com o ano anterior."""
    last = parse_month(until) if until else current_month()
    return TrendsOut.model_validate(insights.trends(db, user, last, months))


# ---------------------------------------------------------------- investimentos


@router.get("/investments")
def list_investments(user: CurrentUser, db: DbSession) -> list[InvestmentOut]:
    return [InvestmentOut.model_validate(i) for i in investments.list_investments(db, user)]


@router.post("/investments", status_code=status.HTTP_201_CREATED)
def create_investment(body: InvestmentIn, user: CurrentUser, db: DbSession) -> InvestmentOut:
    return InvestmentOut.model_validate(investments.create_investment(db, user, body.model_dump()))


@router.patch("/investments/{investment_id}")
def update_investment(
    investment_id: uuid.UUID, body: InvestmentPatch, user: CurrentUser, db: DbSession
) -> InvestmentOut:
    changes = _changes(body, nullable={"institution", "notes"})
    return InvestmentOut.model_validate(
        investments.update_investment(db, user, investment_id, changes)
    )


@router.delete("/investments/{investment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_investment(investment_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    investments.delete_investment(db, user, investment_id)


@router.get("/indicators")
def get_indicators(_: CurrentUser) -> IndicatorsOut:
    """Selic, CDI e IPCA (Banco Central). Exige login só para não virar proxy público."""
    return IndicatorsOut.model_validate(indicators.get_indicators())
