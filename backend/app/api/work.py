"""Rotas da API de Projetos & Tarefas (/api/work/projects) e Agenda & Compromissos (/api/agenda)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, DbSession, require_solution
from app.core.months import today_local
from app.schemas.budget import SafeDate
from app.services import admin as admin_service
from app.services.commerce import shared as commerce_shared
from app.services.work import agenda as agenda_service
from app.services.work import projects as projects_service

projects_router = APIRouter(
    prefix="/work/projects",
    tags=["projetos"],
    dependencies=[Depends(require_solution("projetos"))],
)

agenda_router = APIRouter(
    prefix="/agenda",
    tags=["agenda"],
    dependencies=[Depends(require_solution("agenda"))],
)


# ---------------------------------------------------------------- schemas


class ProjectIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=140)
    description: str | None = Field(default=None, max_length=4000)
    status: Literal["planning", "active", "review", "done", "paused"] = "planning"
    contact_id: uuid.UUID | None = None
    crm_deal_id: uuid.UUID | None = None
    proposal_id: uuid.UUID | None = None
    budget_project_id: uuid.UUID | None = None
    budget_value: Decimal = Field(default=Decimal("0"))
    hourly_rate: Decimal = Field(default=Decimal("0"))
    start_date: date | None = None
    due_date: date | None = None
    link_budget_tag: bool = True


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, max_length=140)
    description: str | None = Field(default=None, max_length=4000)
    status: Literal["planning", "active", "review", "done", "paused"] | None = None
    contact_id: uuid.UUID | None = None
    budget_value: Decimal | None = None
    hourly_rate: Decimal | None = None
    start_date: date | None = None
    due_date: date | None = None


class ChecklistItemIn(BaseModel):
    id: str | None = Field(default=None, max_length=64)
    text: str = Field(..., min_length=1, max_length=160)
    done: bool = False


class TaskIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=4000)
    status: Literal["todo", "doing", "done"] = "todo"
    priority: Literal["low", "medium", "high", "urgent"] = "medium"
    due_date: date | None = None
    checklist: list[ChecklistItemIn] = Field(default_factory=list)


class TaskPatch(BaseModel):
    title: str | None = Field(default=None, max_length=160)
    description: str | None = Field(default=None, max_length=4000)
    status: Literal["todo", "doing", "done"] | None = None
    priority: Literal["low", "medium", "high", "urgent"] | None = None
    due_date: date | None = None
    checklist: list[ChecklistItemIn] | None = None
    position: int | None = None


class TimeEntryIn(BaseModel):
    task_id: uuid.UUID | None = None
    hours: Decimal
    entry_date: date
    notes: str | None = Field(default=None, max_length=240)


class AgendaEventIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=160)
    kind: Literal["meeting", "delivery", "visit", "reminder", "personal"] = "meeting"
    start_at: datetime
    end_at: datetime | None = None
    all_day: bool = False
    location: str | None = Field(default=None, max_length=180)
    status: Literal["scheduled", "confirmed", "done", "cancelled"] = "scheduled"
    contact_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    messaging_chat_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=4000)


class AgendaEventPatch(BaseModel):
    title: str | None = Field(default=None, max_length=160)
    kind: Literal["meeting", "delivery", "visit", "reminder", "personal"] | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    all_day: bool | None = None
    location: str | None = Field(default=None, max_length=180)
    status: Literal["scheduled", "confirmed", "done", "cancelled"] | None = None
    contact_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    messaging_chat_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=4000)


class WhatsappConfirmIn(BaseModel):
    send_now: bool = False
    custom_text: str | None = Field(default=None, max_length=2000)


# ---------------------------------------------------------------- Projetos & Tarefas


@projects_router.get("/hub/bridges")
def get_projects_bridges(user: CurrentUser, db: DbSession) -> dict[str, Any]:
    blocked = admin_service.effective_blocked_resources(db, user)
    res = projects_service.list_projects_hub_bridges(db, user.id)
    return {
        "contacts": [] if "dashboard-crm" in blocked else res["contacts"],
        "deals": [] if "dashboard-crm" in blocked else res["deals"],
        "chats": [] if "mensageria" in blocked else res["chats"],
        "proposals": [] if "propostas" in blocked else res["proposals"],
        "budget_tags": [] if "meu-orcamento" in blocked else res["budget_tags"],
    }


@projects_router.get("")
def list_projects(
    user: CurrentUser,
    db: DbSession,
    status_filter: Annotated[
        Literal["planning", "active", "review", "done", "paused"] | None,
        Query(alias="status"),
    ] = None,
) -> list[dict[str, Any]]:
    return projects_service.list_projects(db, user.id, status_filter=status_filter)


@projects_router.post("", status_code=status.HTTP_201_CREATED)
def create_project(body: ProjectIn, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    return projects_service.create_project(db, user.id, body.model_dump())


@projects_router.get("/{project_id}")
def get_project_detail(project_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    return projects_service.get_project_detail(db, user.id, project_id)


@projects_router.patch("/{project_id}")
def patch_project(
    project_id: uuid.UUID, body: ProjectPatch, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    return projects_service.update_project(
        db, user.id, project_id, body.model_dump(exclude_unset=True)
    )


@projects_router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_project(project_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    projects_service.delete_project(db, user.id, project_id)


@projects_router.post("/{project_id}/tasks", status_code=status.HTTP_201_CREATED)
def create_project_task(
    project_id: uuid.UUID, body: TaskIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    payload = body.model_dump()
    payload["checklist"] = [c.model_dump() for c in body.checklist]
    return projects_service.create_task(db, user.id, project_id, payload)


@projects_router.patch("/tasks/{task_id}")
def patch_project_task(
    task_id: uuid.UUID, body: TaskPatch, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    changes = body.model_dump(exclude_unset=True)
    if "checklist" in changes and body.checklist is not None:
        changes["checklist"] = [c.model_dump() for c in body.checklist]
    return projects_service.update_task(db, user.id, task_id, changes)


@projects_router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_project_task(task_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    projects_service.delete_task(db, user.id, task_id)


@projects_router.post("/{project_id}/time-entries", status_code=status.HTTP_201_CREATED)
def add_project_time_entry(
    project_id: uuid.UUID, body: TimeEntryIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    return projects_service.create_time_entry(db, user.id, project_id, body.model_dump())


@projects_router.delete("/time-entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_project_time_entry(entry_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    projects_service.delete_time_entry(db, user.id, entry_id)


# ---------------------------------------------------------------- Agenda & Compromissos


@agenda_router.get("/hub/bridges")
def get_agenda_bridges(user: CurrentUser, db: DbSession) -> dict[str, Any]:
    blocked = admin_service.effective_blocked_resources(db, user)
    base = commerce_shared.list_hub_bridges(db, user.id)
    projects = [] if "projetos" in blocked else projects_service.list_projects(db, user.id)
    return {
        "contacts": [] if "dashboard-crm" in blocked else base["contacts"],
        "chats": [] if "mensageria" in blocked else base["chats"],
        "projects": [{"id": p["id"], "name": p["name"], "status": p["status"]} for p in projects],
    }


@agenda_router.get("/timeline")
def get_agenda_timeline(
    user: CurrentUser,
    db: DbSession,
    start: Annotated[SafeDate | None, Query()] = None,
    end: Annotated[SafeDate | None, Query()] = None,
    layers: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    ref = today_local()
    start_d = start or ref.replace(day=1)
    end_d = end or (start_d + timedelta(days=34))
    selected = {part.strip() for part in layers.split(",") if part.strip()} if layers else None
    return agenda_service.timeline_360(
        db, user, start_date=start_d, end_date=end_d, layers=selected
    )


@agenda_router.post("/events", status_code=status.HTTP_201_CREATED)
def create_agenda_event(body: AgendaEventIn, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    return agenda_service.create_event(db, user.id, body.model_dump())


@agenda_router.patch("/events/{event_id}")
def patch_agenda_event(
    event_id: uuid.UUID, body: AgendaEventPatch, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    return agenda_service.update_event(db, user.id, event_id, body.model_dump(exclude_unset=True))


@agenda_router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_agenda_event(event_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    agenda_service.delete_event(db, user.id, event_id)


@agenda_router.post("/events/{event_id}/confirm-whatsapp")
def confirm_event_whatsapp(
    event_id: uuid.UUID, body: WhatsappConfirmIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    return agenda_service.prepare_whatsapp_confirmation(
        db, user, event_id, send_now=body.send_now, custom_text=body.custom_text
    )
