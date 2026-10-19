from typing import Annotated, Literal

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.analysis import (
    AssetOut,
    MarketOverview,
    PortfolioOut,
    Quote,
    SimulationOut,
    WatchIn,
)
from app.services import market

router = APIRouter(prefix="/market", tags=["mercado"])


@router.get("/overview")
def overview(_: CurrentUser) -> MarketOverview:
    """Índices, moedas, cripto, maiores altas/baixas e renda fixa (informativo)."""
    return MarketOverview.model_validate(market.overview())


@router.get("/asset/{symbol}")
def asset(
    symbol: str, _: CurrentUser, range: Literal["5d", "1mo", "3mo", "1y"] = "1mo"
) -> AssetOut:
    return AssetOut.model_validate(market.asset(symbol, range))


@router.get("/quotes")
def quotes(_: CurrentUser, symbols: Annotated[str, Query(max_length=200)]) -> list[Quote]:
    wanted = [s for s in symbols.split(",") if s.strip()][:20]
    found = market.quotes(wanted)
    return [Quote.model_validate(q) for q in found.values()]


@router.get("/watchlist")
def watchlist(user: CurrentUser, db: DbSession) -> list[Quote]:
    return [Quote.model_validate(q) for q in market.watch_quotes(db, user)]


@router.post("/watchlist", status_code=status.HTTP_201_CREATED)
def add_watch(body: WatchIn, user: CurrentUser, db: DbSession) -> dict[str, str]:
    return {"symbol": market.add_watch(db, user, body.symbol).symbol}


@router.delete("/watchlist/{symbol}", status_code=status.HTTP_204_NO_CONTENT)
def remove_watch(symbol: str, user: CurrentUser, db: DbSession) -> None:
    market.remove_watch(db, user, symbol)


@router.get("/fixed-income/simulate")
def simulate(
    _: CurrentUser,
    amount: Annotated[float, Query(gt=0, le=100_000_000)],
    months: Annotated[int, Query(ge=1, le=600)],
    cdb_pct: Annotated[float, Query(ge=50, le=200)] = 100,
) -> SimulationOut:
    return SimulationOut.model_validate(market.simulate_fixed_income(amount, months, cdb_pct))


@router.post("/portfolio/refresh")
def refresh_portfolio(user: CurrentUser, db: DbSession) -> PortfolioOut:
    """Atualiza o valor dos investimentos com código e quantidade pela cotação do momento."""
    return PortfolioOut.model_validate(market.refresh_portfolio(db, user))
