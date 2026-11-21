"""Rotas da API Dashboard & CRM (/api/crm/*) integradas à conta autenticada do Hub."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from pydantic import BaseModel, Field, field_validator

from app.api.deps import CurrentUser, DbSession, require_feature, require_solution
from app.core.errors import AppError
from app.core.money import MONEY_RANGE_MESSAGE
from app.core.rate_limit import limiter
from app.services import admin as admin_service
from app.services.crm import (
    api_connector,
    csv_reader,
    hub_bridge,
    pdf_reader,
)
from app.services.crm import crm as crm_service
from app.services.crm import dashboards as dashboards_service
from app.services.crm import sources as sources_service
from app.services.crm.parsing import parse_money

router = APIRouter(
    prefix="/crm",
    tags=["dashboard-crm"],
    dependencies=[Depends(require_solution("dashboard-crm"))],
)


def _limit_api(user: CurrentUser) -> None:
    if limiter.hit(f"crm-api:{user.id}", 20, 60) is not None:
        raise AppError(
            429, "rate_limited", "Muitas consultas de API. Tente novamente em um minuto."
        )


def _limit_pdf_csv(user: CurrentUser) -> None:
    if limiter.hit(f"crm-pdf:{user.id}", 5, 60) is not None:
        raise AppError(
            429,
            "rate_limited",
            "Muitas leituras de PDF/CSV seguidas. Tente novamente em um minuto.",
        )


# ---------------------------------------------------------------- status e pontes Hub


@router.get("/hub/messaging-chats")
def get_hub_messaging_chats(user: CurrentUser, db: DbSession) -> list[dict[str, Any]]:
    admin_service.assert_resource_allowed(db, user, "mensageria")
    return hub_bridge.list_messaging_chats_for_link(db, user)


# ---------------------------------------------------------------- CRM: funil, contatos e negócios


class ContactIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=160)
    company: str | None = Field(default=None, max_length=120)
    origin: str | None = Field(default=None, max_length=60)
    tags: list[str] = Field(default_factory=list)
    notes: str | None = Field(default=None, max_length=2000)
    messaging_chat_id: uuid.UUID | None = None
    budget_person: str | None = Field(default=None, max_length=80)


class ContactPatch(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=160)
    company: str | None = Field(default=None, max_length=120)
    origin: str | None = Field(default=None, max_length=60)
    tags: list[str] | None = None
    notes: str | None = Field(default=None, max_length=2000)
    messaging_chat_id: uuid.UUID | None = None
    budget_person: str | None = Field(default=None, max_length=80)


class DealIn(BaseModel):
    title: str = Field(min_length=1, max_length=140)
    value: Decimal = Decimal("0")
    stage_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    expected_close_date: date | None = None
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("value", mode="before")
    @classmethod
    def _parse_br_money(cls, raw: object) -> Decimal:
        if raw in (None, ""):
            return Decimal("0")
        parsed = parse_money(raw)
        if parsed is None:
            raise ValueError(MONEY_RANGE_MESSAGE)
        return parsed


class DealPatch(BaseModel):
    title: str | None = Field(default=None, max_length=140)
    value: Decimal | None = None
    stage_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    expected_close_date: date | None = None
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("value", mode="before")
    @classmethod
    def _parse_br_money(cls, raw: object) -> Decimal | None:
        if raw in (None, ""):
            return None
        parsed = parse_money(raw)
        if parsed is None:
            raise ValueError(MONEY_RANGE_MESSAGE)
        return parsed


class ActivityIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    kind: Literal["note", "task", "call", "message", "budget"] = "note"
    contact_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None
    due_at: datetime | None = None


class ActivityDoneIn(BaseModel):
    done: bool = True


@router.get("/pipeline")
def get_pipeline(user: CurrentUser, db: DbSession) -> dict[str, Any]:
    return crm_service.get_pipeline_board(db, user.id)


@router.get("/contacts")
def list_contacts(
    user: CurrentUser,
    db: DbSession,
    q: Annotated[str | None, Query(max_length=120)] = None,
) -> list[dict[str, Any]]:
    return crm_service.list_contacts(db, user.id, q=q)


@router.post("/contacts", status_code=status.HTTP_201_CREATED)
def create_contact(body: ContactIn, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    return crm_service.create_contact(db, user.id, body.model_dump())


@router.post("/contacts/from-messaging/{chat_id}")
def import_contact_from_messaging(
    chat_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    admin_service.assert_resource_allowed(db, user, "mensageria")
    contact, created = hub_bridge.import_contact_from_messaging(db, user, chat_id)
    return {"contact": crm_service.serialize_contact(contact), "created": created}


@router.patch("/contacts/{contact_id}")
def patch_contact(
    contact_id: uuid.UUID, body: ContactPatch, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    return crm_service.update_contact(db, user.id, contact_id, body.model_dump(exclude_unset=True))


@router.delete("/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_contact(contact_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    crm_service.delete_contact(db, user.id, contact_id)


@router.post("/deals", status_code=status.HTTP_201_CREATED)
def create_deal(body: DealIn, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    return crm_service.create_deal(db, user.id, body.model_dump())


@router.patch("/deals/{deal_id}")
def patch_deal(
    deal_id: uuid.UUID, body: DealPatch, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    return crm_service.update_deal(db, user.id, deal_id, body.model_dump(exclude_unset=True))


@router.delete("/deals/{deal_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_deal(deal_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    crm_service.delete_deal(db, user.id, deal_id)


@router.post("/deals/{deal_id}/sync-budget")
def sync_deal_budget(deal_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    admin_service.assert_resource_allowed(db, user, "meu-orcamento")
    deal = crm_service.get_deal(db, user.id, deal_id)
    return hub_bridge.sync_won_deal_to_budget(db, user, deal)


@router.post("/deals/{deal_id}/create-project", status_code=status.HTTP_201_CREATED)
def create_deal_project(deal_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    from app.services.work.projects import create_project_from_crm_deal

    return create_project_from_crm_deal(db, user, deal_id)


@router.get("/activities")
def list_activities(
    user: CurrentUser,
    db: DbSession,
    contact_id: Annotated[uuid.UUID | None, Query()] = None,
    deal_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[dict[str, Any]]:
    rows = crm_service.list_activities(db, user.id, contact_id=contact_id, deal_id=deal_id)
    return [
        {
            "id": a.id,
            "contact_id": a.contact_id,
            "deal_id": a.deal_id,
            "kind": a.kind,
            "body": a.body,
            "due_at": a.due_at,
            "done_at": a.done_at,
            "created_at": a.created_at,
        }
        for a in rows
    ]


@router.post("/activities", status_code=status.HTTP_201_CREATED)
def create_activity(body: ActivityIn, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    a = crm_service.create_activity(
        db,
        user.id,
        body=body.body,
        kind=body.kind,
        contact_id=body.contact_id,
        deal_id=body.deal_id,
        due_at=body.due_at,
    )
    return {
        "id": a.id,
        "contact_id": a.contact_id,
        "deal_id": a.deal_id,
        "kind": a.kind,
        "body": a.body,
        "due_at": a.due_at,
        "done_at": a.done_at,
        "created_at": a.created_at,
    }


@router.patch("/activities/{activity_id}")
def patch_activity(
    activity_id: uuid.UUID, body: ActivityDoneIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    a = crm_service.toggle_activity_done(db, user.id, activity_id, body.done)
    return {
        "id": a.id,
        "contact_id": a.contact_id,
        "deal_id": a.deal_id,
        "kind": a.kind,
        "body": a.body,
        "due_at": a.due_at,
        "done_at": a.done_at,
        "created_at": a.created_at,
    }


# ---------------------------------------------------------------- Fontes de Dados (PDF, CSV, API)


class ColumnDefIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    label: str = Field(min_length=1, max_length=60)
    type: Literal["text", "number", "currency", "date", "phone", "email", "boolean"] = "text"


class SaveTabularSourceIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["pdf", "csv"]
    description: str | None = Field(default=None, max_length=300)
    columns: list[ColumnDefIn] = Field(min_length=1, max_length=100)
    rows: list[dict[str, Any]] = Field(default_factory=list, max_length=5000)
    source_id: uuid.UUID | None = None
    mode: Literal["replace", "append"] = "replace"
    dedupe_key: str | None = Field(default=None, max_length=60)
    config: dict[str, Any] | None = None
    create_dashboard: bool = False


class ImportToCrmIn(BaseModel):
    target: Literal["contacts", "deals"]
    rows: list[dict[str, Any]] = Field(min_length=1, max_length=2000)
    mapping: dict[str, str]
    origin: str = Field(default="Importação PDF/CSV", max_length=60)


class ApiPreviewIn(BaseModel):
    url: str = Field(min_length=8, max_length=500)
    method: Literal["GET", "POST"] = "GET"
    data_path: str | None = Field(default=None, max_length=120)
    auth_type: Literal["none", "bearer", "api_key", "basic"] = "none"
    auth_value: str | None = Field(default=None, max_length=500)
    header_name: str | None = Field(default=None, max_length=80)


class CreateApiSourceIn(ApiPreviewIn):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=300)
    sync_now: bool = True


@router.get("/sources")
def list_sources(user: CurrentUser, db: DbSession) -> list[dict[str, Any]]:
    return sources_service.list_sources(db, user.id)


@router.get("/sources/{source_id}/rows")
def get_source_rows(
    source_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> dict[str, Any]:
    src = sources_service.get_source(db, user.id, source_id)
    schema, rows = sources_service.load_source_data(db, user.id, src)
    return {
        "source": sources_service.serialize_source(db, user.id, src),
        "columns": schema,
        "rows": rows[:limit],
        "total_rows": len(rows),
    }


@router.post(
    "/sources/preview/pdf",
    dependencies=[Depends(require_feature("feature:pdf_ocr_upload"))],
)
def preview_pdf(
    user: CurrentUser,
    file: Annotated[UploadFile, File()],
) -> dict[str, Any]:
    _limit_pdf_csv(user)
    content = file.file.read(pdf_reader.MAX_PDF_BYTES + 1)
    extracted = pdf_reader.extract_pdf(content, filename=file.filename or "documento.pdf")
    return {
        "filename": file.filename or "documento.pdf",
        "strategy": extracted.strategy,
        "used_ocr": extracted.used_ocr,
        "pages": extracted.pages,
        "ocr_pages": extracted.ocr_pages,
        "raw_text_excerpt": extracted.raw_text_excerpt,
        "columns": extracted.columns,
        "rows": extracted.rows[:200],
        "total_rows": len(extracted.rows),
        "suggestions": extracted.suggestions,
        "warning": extracted.warning,
    }


@router.post(
    "/sources/preview/csv",
    dependencies=[Depends(require_feature("feature:pdf_ocr_upload"))],
)
def preview_csv(
    user: CurrentUser,
    file: Annotated[UploadFile, File()],
    delimiter: Annotated[str | None, Form()] = None,
) -> dict[str, Any]:
    _limit_pdf_csv(user)
    content = file.file.read(csv_reader.MAX_CSV_BYTES + 1)
    extracted = csv_reader.extract_csv(content, delimiter=delimiter or None)
    return {
        "filename": file.filename or "planilha.csv",
        **extracted,
        "rows": extracted["rows"][:200],
    }


@router.post("/sources/tabular", status_code=status.HTTP_201_CREATED)
def save_tabular_source(
    body: SaveTabularSourceIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    saved = sources_service.save_tabular_source(
        db,
        user.id,
        name=body.name,
        kind=body.kind,
        columns=[c.model_dump() for c in body.columns],
        rows=body.rows,
        description=body.description,
        config=body.config,
        source_id=body.source_id,
        mode=body.mode,
        dedupe_key=body.dedupe_key,
    )
    dashboard = None
    if body.create_dashboard:
        dashboard = dashboards_service.create_dashboard(
            db,
            user.id,
            name=f"Painel · {saved['name']}"[:100],
            description=f"Gerado automaticamente a partir da fonte {saved['name']}.",
            template="dataset",
            source_id=saved["id"],
        )
    return {"source": saved, "dashboard": dashboard}


@router.post("/sources/import-to-crm")
def import_to_crm(body: ImportToCrmIn, user: CurrentUser, db: DbSession) -> dict[str, int]:
    if body.target == "contacts":
        return crm_service.import_rows_to_contacts(
            db, user.id, body.rows, body.mapping, origin=body.origin
        )
    return crm_service.import_rows_to_deals(
        db, user.id, body.rows, body.mapping, origin=body.origin
    )


@router.post(
    "/sources/preview/api",
    dependencies=[Depends(require_feature("feature:external_api"))],
)
def preview_api(body: ApiPreviewIn, user: CurrentUser) -> dict[str, Any]:
    _limit_api(user)
    encrypted = api_connector.encrypt_credentials(body.auth_type, body.auth_value, body.header_name)
    fetched = api_connector.fetch_external_api(
        url=body.url,
        method=body.method,
        data_path=body.data_path,
        credentials_encrypted=encrypted,
    )
    return {
        "columns": fetched["columns"],
        "rows": fetched["rows"][:100],
        "total_rows": fetched["total_rows"],
        "suggestions": fetched["suggestions"],
    }


@router.post(
    "/sources/api",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_feature("feature:external_api"))],
)
def create_api_source(body: CreateApiSourceIn, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    _limit_api(user)
    return sources_service.create_api_source(
        db,
        user.id,
        name=body.name,
        url=body.url,
        method=body.method,
        data_path=body.data_path,
        auth_type=body.auth_type,
        auth_value=body.auth_value,
        header_name=body.header_name,
        description=body.description,
        sync_now=body.sync_now,
    )


@router.post(
    "/sources/{source_id}/sync",
    dependencies=[Depends(require_feature("feature:external_api"))],
)
def sync_source(source_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    sources_service.get_source(db, user.id, source_id)
    _limit_api(user)
    return sources_service.sync_api_source(db, user.id, source_id)


@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_source(source_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    sources_service.delete_source(db, user.id, source_id)


# ---------------------------------------------------------------- Dashboards e Widgets


class DashboardIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=240)
    template: Literal[
        "blank", "crm_overview", "messaging_overview", "budget_overview", "dataset"
    ] = "blank"
    source_id: uuid.UUID | None = None


class WidgetIn(BaseModel):
    source_id: uuid.UUID
    title: str = Field(min_length=1, max_length=100)
    widget_type: Literal["kpi", "bar", "line", "donut", "funnel", "table"]
    span: Literal[1, 2] = 1
    query: dict[str, Any] = Field(default_factory=dict)


class WidgetPatch(BaseModel):
    source_id: uuid.UUID | None = None
    title: str | None = Field(default=None, max_length=100)
    widget_type: Literal["kpi", "bar", "line", "donut", "funnel", "table"] | None = None
    span: Literal[1, 2] | None = None
    position: int | None = None
    query: dict[str, Any] | None = None


@router.get("/dashboards")
def list_dashboards(user: CurrentUser, db: DbSession) -> list[dict[str, Any]]:
    return dashboards_service.list_dashboards(db, user.id)


@router.post("/dashboards", status_code=status.HTTP_201_CREATED)
def create_dashboard(body: DashboardIn, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    return dashboards_service.create_dashboard(
        db,
        user.id,
        name=body.name,
        description=body.description,
        template=body.template,
        source_id=body.source_id,
    )


@router.get("/dashboards/{dashboard_id}")
def get_dashboard(
    dashboard_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    date_range: Annotated[
        Literal["all", "7d", "30d", "90d", "month", "year"] | None, Query()
    ] = None,
) -> dict[str, Any]:
    return dashboards_service.get_dashboard_view(db, user.id, dashboard_id, date_range=date_range)


@router.delete("/dashboards/{dashboard_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_dashboard(dashboard_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    dashboards_service.delete_dashboard(db, user.id, dashboard_id)


@router.post("/dashboards/{dashboard_id}/widgets", status_code=status.HTTP_201_CREATED)
def create_widget(
    dashboard_id: uuid.UUID, body: WidgetIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    return dashboards_service.add_widget(
        db,
        user.id,
        dashboard_id,
        source_id=body.source_id,
        title=body.title,
        widget_type=body.widget_type,
        span=body.span,
        query=body.query,
    )


@router.patch("/widgets/{widget_id}")
def patch_widget(
    widget_id: uuid.UUID, body: WidgetPatch, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    return dashboards_service.update_widget(
        db, user.id, widget_id, body.model_dump(exclude_unset=True)
    )


@router.delete("/widgets/{widget_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_widget(widget_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    dashboards_service.delete_widget(db, user.id, widget_id)
