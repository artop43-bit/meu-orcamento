import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, Field

from app.api.budget import _changes
from app.api.deps import CurrentUser, DbSession
from app.core.months import current_month, format_month, parse_month
from app.schemas.analysis import (
    AnalysisConfig,
    CompareOut,
    IndicatorsOut,
    InsightsOut,
    InvestmentIn,
    InvestmentOut,
    InvestmentPatch,
    OverviewOut,
    ProjectionPoint,
    RuleOut,
    SavedAnalysisIn,
    SavedAnalysisOut,
    SavedAnalysisPatch,
    ScoreOut,
    SeriesOut,
    TrendsOut,
)
from app.services import analysis, indicators, insights, investments, series

router = APIRouter(tags=["análises"])


# ---------------------------------------------------------------- análises


@router.get("/analysis/overview")
def overview(user: CurrentUser, db: DbSession, month: str | None = None) -> OverviewOut:
    """Score financeiro e regra 50/30/20 do mês (padrão: mês atual)."""
    target = parse_month(month) if month else current_month(user.month_start_day)
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
    first = parse_month(start) if start else current_month(user.month_start_day)
    return [ProjectionPoint.model_validate(p) for p in analysis.projection(db, user, first, months)]


@router.get("/analysis/insights")
def get_insights(user: CurrentUser, db: DbSession, month: str | None = None) -> InsightsOut:
    """Leitura do mês pelo "consultor": resumo, elogios, alertas e próximos passos."""
    target = parse_month(month) if month else current_month(user.month_start_day)
    return InsightsOut.model_validate(insights.consultant(db, user, target))


@router.get("/analysis/trends")
def get_trends(
    user: CurrentUser,
    db: DbSession,
    until: str | None = None,
    months: Annotated[int, Query(ge=3, le=24)] = 12,
) -> TrendsOut:
    """Evolução de renda, gastos e categorias, médias e comparação com o ano anterior."""
    last = parse_month(until) if until else current_month(user.month_start_day)
    return TrendsOut.model_validate(insights.trends(db, user, last, months))


@router.post("/analysis/series")
def get_series(config: AnalysisConfig, user: CurrentUser, db: DbSession) -> SeriesOut:
    """Monta os dados de uma análise personalizada (o quê, período, agrupamento, comparação)."""
    return SeriesOut.model_validate(series.build(db, user, config.model_dump(mode="json")))


@router.get("/analysis/saved")
def list_saved(user: CurrentUser, db: DbSession) -> list[SavedAnalysisOut]:
    return [SavedAnalysisOut.model_validate(s) for s in series.list_saved(db, user)]


@router.post("/analysis/saved", status_code=status.HTTP_201_CREATED)
def create_saved(body: SavedAnalysisIn, user: CurrentUser, db: DbSession) -> SavedAnalysisOut:
    item = series.create_saved(
        db, user, body.name, body.config.model_dump(mode="json"), body.pinned
    )
    return SavedAnalysisOut.model_validate(item)


@router.patch("/analysis/saved/{item_id}")
def update_saved(
    item_id: uuid.UUID, body: SavedAnalysisPatch, user: CurrentUser, db: DbSession
) -> SavedAnalysisOut:
    changes = body.model_dump(mode="json", exclude_unset=True, exclude_none=True)
    return SavedAnalysisOut.model_validate(series.update_saved(db, user, item_id, changes))


@router.delete("/analysis/saved/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved(item_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    series.delete_saved(db, user, item_id)


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


class InflationOut(BaseModel):
    amount: float
    corrected: float
    inflation_pct: float
    start: str
    end: str
    months: int
    last_available: str


@router.get("/analysis/fees")
def fees(
    user: CurrentUser, db: DbSession, year: Annotated[int, Query(ge=2000, le=2100)]
) -> dict[str, Any]:
    """v1.4: tarifas, anuidades, IOF, juros e multas pagos no ano."""
    from app.services import xray

    return xray.fees(db, user, year)


@router.get("/analysis/personal-inflation")
def personal_inflation(user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """v1.4: quanto subiram os gastos por categoria (12 meses × 12 anteriores) contra o IPCA."""
    from app.services import xray

    return xray.personal_inflation(db, user)


@router.get("/indicators/inflation")
def inflation(
    _: CurrentUser,
    amount: Annotated[float, Query(gt=0, le=1_000_000_000)],
    start: Annotated[str, Query(pattern=r"^\d{4}-\d{2}$")],
    end: Annotated[str, Query(pattern=r"^\d{4}-\d{2}$")],
) -> InflationOut:
    """Quanto um valor de um mês antigo vale hoje, corrigido pelo IPCA (Banco Central)."""
    return InflationOut.model_validate(indicators.correct_by_inflation(amount, start, end))


@router.get("/indicators")
def get_indicators(_: CurrentUser) -> IndicatorsOut:
    """Selic, CDI e IPCA (Banco Central). Exige login só para não virar proxy público."""
    return IndicatorsOut.model_validate(indicators.get_indicators())


# ---------------------------------------------------------------- meta de alocação (v1.4)


class TargetsIn(BaseModel):
    # Percentual por classe da carteira (soma 100). Vazio apaga a meta.
    targets: dict[str, Annotated[float, Field(ge=0, le=100)]] = Field(default_factory=dict)


@router.get("/investments/targets")
def get_targets(user: CurrentUser) -> dict[str, float]:
    import json

    return json.loads(user.investment_targets) if user.investment_targets else {}


@router.put("/investments/targets")
def set_targets(body: TargetsIn, user: CurrentUser, db: DbSession) -> dict[str, float]:
    import json

    from app.core.errors import AppError

    targets = {k[:20]: round(v, 1) for k, v in body.targets.items() if v > 0}
    if targets and abs(sum(targets.values()) - 100) > 0.5:
        raise AppError(400, "invalid_targets", "Os percentuais da meta precisam somar 100%.")
    if len(targets) > 12:
        raise AppError(400, "invalid_targets", "No máximo 12 classes na meta.")
    user.investment_targets = json.dumps(targets) if targets else None
    db.commit()
    return targets
