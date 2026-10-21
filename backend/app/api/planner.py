import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel

from app.api.budget import _changes
from app.api.deps import CurrentUser, DbSession
from app.core.months import format_month, parse_month
from app.core.rate_limit import rate_limit
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


# ---------------------------------------------------------------- agenda do celular (v1.4)


class CalendarLinkOut(BaseModel):
    url: str | None


def _feed_url(token: str | None) -> str | None:
    from app.core.config import get_settings

    return f"{get_settings().frontend_url}/api/calendar-feed/{token}.ics" if token else None


@router.get("/calendar-link")
def calendar_link(user: CurrentUser) -> CalendarLinkOut:
    return CalendarLinkOut(url=_feed_url(user.calendar_token))


@router.post("/calendar-link")
def new_calendar_link(user: CurrentUser, db: DbSession) -> CalendarLinkOut:
    """Cria (ou troca) o link secreto: o anterior para de funcionar na hora."""
    from app.services import ical

    return CalendarLinkOut(url=_feed_url(ical.new_token(db, user)))


@router.delete("/calendar-link", status_code=status.HTTP_204_NO_CONTENT)
def delete_calendar_link(user: CurrentUser, db: DbSession) -> None:
    from app.services import ical

    ical.revoke(db, user)


@router.get(
    "/calendar-feed/{token}.ics",
    dependencies=[Depends(rate_limit("calendar_feed", 60, 3600))],
)
def calendar_feed(token: str, db: DbSession) -> Response:
    """Calendário iCal (sem login: o código secreto do link identifica a pessoa)."""
    from app.services import ical

    user = ical.owner(db, token)
    return Response(
        content=ical.build(db, user),
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'inline; filename="meu-orcamento.ics"'},
    )
