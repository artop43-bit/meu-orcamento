"""v1.3: painel de erros. As telas enviam os erros que acontecem; a administração acompanha."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field, StringConstraints

from app.api.deps import AdminUser, CurrentUser, DbSession
from app.core.rate_limit import rate_limit
from app.services import errors, perf

router = APIRouter(tags=["erros"])

Short = Annotated[str, StringConstraints(max_length=300)]


class ErrorIn(BaseModel):
    name: Annotated[str, StringConstraints(max_length=80)] | None = None
    message: Short | None = None
    path: Annotated[str, StringConstraints(max_length=300)] | None = None
    release: Annotated[str, StringConstraints(max_length=20)] | None = None
    detail: Annotated[str, StringConstraints(max_length=4000)] | None = None


class ErrorOut(BaseModel):
    id: uuid.UUID
    source: str
    name: str
    message: str
    path: str | None
    detail: str | None
    user_agent: str | None
    release: str | None
    count: int
    first_seen: datetime
    last_seen: datetime
    resolved_at: datetime | None


@router.post(
    "/errors",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(rate_limit("errors", 30, 600))],
)
def report(body: ErrorIn, request: Request, db: DbSession) -> None:
    """Erro de uma tela (sem login: também vale para a tela de entrar)."""
    errors.record(
        db,
        source="web",
        name=body.name,
        message=body.message,
        path=body.path,
        user_agent=request.headers.get("user-agent"),
        release=body.release,
        detail=body.detail,
    )


@router.get("/admin/errors")
def list_errors(_: AdminUser, db: DbSession) -> list[ErrorOut]:
    return [ErrorOut.model_validate(e, from_attributes=True) for e in errors.overview(db)]


@router.post("/admin/errors/{event_id}/resolve", status_code=status.HTTP_204_NO_CONTENT)
def resolve_error(event_id: uuid.UUID, _: AdminUser, db: DbSession) -> None:
    errors.resolve(db, event_id)


# ---------------------------------------------------------------- velocidade das telas (v1.7.5)


class PerfSample(BaseModel):
    screen: Annotated[str, StringConstraints(max_length=40)]
    load_ms: int = Field(ge=1, le=60_000)
    frame_ms: int = Field(default=0, ge=0, le=60_000)


class PerfIn(BaseModel):
    samples: list[PerfSample] = Field(max_length=20)


class PerfRow(BaseModel):
    screen: str
    count: int
    average_ms: int
    max_ms: int
    slow_pct: float
    frame_ms: int


@router.post(
    "/perf",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(rate_limit("perf", 30, 60))],
)
def perf_record(body: PerfIn, _: CurrentUser, db: DbSession) -> None:
    """Tempo de abertura das telas, somado por dia e por tela (não guarda quem enviou)."""
    perf.record(db, [s.model_dump() for s in body.samples])


@router.get("/admin/perf")
def perf_summary(_: AdminUser, db: DbSession, days: int = 7) -> list[PerfRow]:
    return [PerfRow.model_validate(r) for r in perf.summary(db, max(1, min(days, 90)))]
