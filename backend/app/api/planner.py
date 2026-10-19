import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.budget import _changes
from app.api.deps import CurrentUser, DbSession
from app.core.months import format_month, parse_month
from app.schemas.budget import (
    CalendarEvent,
    CalendarOut,
    CategorySuggestion,
    ConfirmPlannedIn,
    DescriptionSuggestion,
    ExpenseOut,
    PlannedIn,
    PlannedOut,
    PlannedPatch,
)
from app.services import planned, suggest

router = APIRouter(tags=["calendário e sugestões"])


# ---------------------------------------------------------------- sugestões


@router.get("/suggest/category")
def suggest_category(
    user: CurrentUser,
    db: DbSession,
    description: Annotated[str, Query(max_length=120)],
) -> CategorySuggestion | None:
    """Categoria provável para a descrição (histórico do usuário, depois palavras-chave)."""
    found = suggest.suggest_category(db, user, description)
    return CategorySuggestion.model_validate(found) if found else None


@router.get("/suggest/descriptions")
def suggest_descriptions(
    user: CurrentUser,
    db: DbSession,
    q: Annotated[str, Query(max_length=120)],
) -> list[DescriptionSuggestion]:
    return [
        DescriptionSuggestion.model_validate(s) for s in suggest.describe_suggestions(db, user, q)
    ]


# ---------------------------------------------------------------- planejados


@router.get("/planned")
def list_planned(user: CurrentUser, db: DbSession, month: str | None = None) -> list[PlannedOut]:
    if month:
        start = parse_month(month)
        items = planned.list_planned(db, user, start, planned.month_end(start))
    else:
        items = planned.list_planned(db, user)
    return [PlannedOut.model_validate(p) for p in items]


@router.post("/planned", status_code=status.HTTP_201_CREATED)
def create_planned(body: PlannedIn, user: CurrentUser, db: DbSession) -> PlannedOut:
    return PlannedOut.model_validate(planned.create_planned(db, user, body.model_dump()))


@router.patch("/planned/{item_id}")
def update_planned(
    item_id: uuid.UUID, body: PlannedPatch, user: CurrentUser, db: DbSession
) -> PlannedOut:
    changes = _changes(body, nullable={"category_id", "notes"})
    return PlannedOut.model_validate(planned.update_planned(db, user, item_id, changes))


@router.delete("/planned/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_planned(item_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    planned.delete_planned(db, user, item_id)


@router.post("/planned/{item_id}/confirm", status_code=status.HTTP_201_CREATED)
def confirm_planned(
    item_id: uuid.UUID, body: ConfirmPlannedIn, user: CurrentUser, db: DbSession
) -> ExpenseOut:
    """Vira conta de verdade no mês da data planejada."""
    return ExpenseOut.model_validate(planned.confirm_planned(db, user, item_id, body.paid))


# ---------------------------------------------------------------- calendário


@router.get("/calendar/{month}")
def get_calendar(month: str, user: CurrentUser, db: DbSession) -> CalendarOut:
    target = parse_month(month)
    events = planned.month_calendar(db, user, target)
    return CalendarOut(
        month=format_month(target), events=[CalendarEvent.model_validate(e) for e in events]
    )
