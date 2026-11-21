"""Rotas da API de Catálogo & Pedidos (/api/catalog) e Propostas em PDF (/api/proposals)."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, DbSession, require_solution
from app.services import admin as admin_service
from app.services.commerce import catalog as catalog_service
from app.services.commerce import proposals as proposals_service
from app.services.commerce import shared as commerce_shared

catalog_router = APIRouter(
    prefix="/catalog",
    tags=["catalogo"],
    dependencies=[Depends(require_solution("catalogo"))],
)

proposals_router = APIRouter(
    prefix="/proposals",
    tags=["propostas"],
    dependencies=[Depends(require_solution("propostas"))],
)


# ---------------------------------------------------------------- schemas


class CatalogItemIn(BaseModel):
    kind: Literal["product", "service"] = "product"
    sku: str | None = Field(default=None, max_length=40)
    name: str = Field(..., min_length=1, max_length=140)
    unit: str = Field(default="un", max_length=16)
    cost_price: Decimal = Field(default=Decimal("0"))
    sale_price: Decimal = Field(default=Decimal("0"))
    stock_qty: Decimal = Field(default=Decimal("0"))
    min_stock: Decimal = Field(default=Decimal("0"))
    active: bool = True
    notes: str | None = Field(default=None, max_length=2000)


class CatalogItemPatch(BaseModel):
    kind: Literal["product", "service"] | None = None
    sku: str | None = Field(default=None, max_length=40)
    name: str | None = Field(default=None, max_length=140)
    unit: str | None = Field(default=None, max_length=16)
    cost_price: Decimal | None = None
    sale_price: Decimal | None = None
    min_stock: Decimal | None = None
    active: bool | None = None
    notes: str | None = Field(default=None, max_length=2000)


class StockMovementIn(BaseModel):
    kind: Literal["in", "out", "adjust"]
    qty: Decimal
    reason: str | None = Field(default=None, max_length=180)


class LineItemIn(BaseModel):
    item_id: uuid.UUID | None = None
    kind: Literal["product", "service"] = "service"
    name: str | None = Field(default=None, max_length=140)
    unit: str | None = Field(default=None, max_length=16)
    qty: Decimal = Field(default=Decimal("1"))
    unit_price: Decimal | None = None


class OrderIn(BaseModel):
    contact_id: uuid.UUID | None = None
    crm_deal_id: uuid.UUID | None = None
    customer_name: str | None = Field(default=None, max_length=140)
    items: list[LineItemIn] = Field(default_factory=list, max_length=200)
    discount: Decimal = Field(default=Decimal("0"))
    notes: str | None = Field(default=None, max_length=2000)
    confirm_now: bool = True
    sync_budget: bool = False
    sync_crm: bool = False


class OrderConfirmIn(BaseModel):
    sync_budget: bool = True
    sync_crm: bool = True


class DocumentIn(BaseModel):
    doc_type: Literal["proposal", "service_order", "contract", "receipt"] = "proposal"
    title: str | None = Field(default=None, max_length=160)
    contact_id: uuid.UUID | None = None
    crm_deal_id: uuid.UUID | None = None
    order_id: uuid.UUID | None = None
    customer_name: str | None = Field(default=None, max_length=140)
    customer_doc: str | None = Field(default=None, max_length=40)
    customer_contact: str | None = Field(default=None, max_length=120)
    items: list[LineItemIn] = Field(default_factory=list, max_length=200)
    discount: Decimal | None = None
    valid_until: date | None = None
    terms_text: str | None = Field(default=None, max_length=6000)


class DocumentPatch(BaseModel):
    title: str | None = Field(default=None, max_length=160)
    customer_doc: str | None = Field(default=None, max_length=40)
    customer_contact: str | None = Field(default=None, max_length=120)
    items: list[LineItemIn] | None = Field(default=None, max_length=200)
    discount: Decimal | None = None
    valid_until: date | None = None
    terms_text: str | None = Field(default=None, max_length=6000)
    status: Literal["draft", "sent", "approved", "rejected", "cancelled"] | None = None


class SendDocumentIn(BaseModel):
    chat_id: uuid.UUID
    caption: str | None = Field(default=None, max_length=2000)


class ApproveDocumentIn(BaseModel):
    sync_crm: bool = True
    sync_budget: bool = True


# ---------------------------------------------------------------- Catálogo & Pedidos


@catalog_router.get("/hub/bridges")
def get_catalog_hub_bridges(user: CurrentUser, db: DbSession) -> dict[str, Any]:
    blocked = admin_service.effective_blocked_resources(db, user)
    if "dashboard-crm" in blocked:
        return {"contacts": [], "deals": []}
    bridges = commerce_shared.list_hub_bridges(db, user.id)
    return {"contacts": bridges["contacts"], "deals": bridges["deals"]}


@catalog_router.get("/items")
def list_catalog_items(
    user: CurrentUser,
    db: DbSession,
    kind: Annotated[Literal["product", "service"] | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
    active_only: Annotated[bool, Query()] = False,
) -> dict[str, Any]:
    return catalog_service.list_items(db, user.id, kind=kind, q=q, active_only=active_only)


@catalog_router.post("/items", status_code=status.HTTP_201_CREATED)
def create_catalog_item(body: CatalogItemIn, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    return catalog_service.create_item(db, user.id, body.model_dump())


@catalog_router.patch("/items/{item_id}")
def patch_catalog_item(
    item_id: uuid.UUID, body: CatalogItemPatch, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    return catalog_service.update_item(db, user.id, item_id, body.model_dump(exclude_unset=True))


@catalog_router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_catalog_item(item_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    catalog_service.delete_item(db, user.id, item_id)


@catalog_router.post("/items/{item_id}/movement")
def post_stock_movement(
    item_id: uuid.UUID, body: StockMovementIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    return catalog_service.adjust_stock(
        db, user.id, item_id, kind=body.kind, qty=body.qty, reason=body.reason
    )


@catalog_router.get("/movements")
def list_stock_movements(
    user: CurrentUser,
    db: DbSession,
    item_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[dict[str, Any]]:
    return catalog_service.list_movements(db, user.id, item_id=item_id)


@catalog_router.get("/orders")
def list_commercial_orders(user: CurrentUser, db: DbSession) -> list[dict[str, Any]]:
    return catalog_service.list_orders(db, user.id)


@catalog_router.post("/orders", status_code=status.HTTP_201_CREATED)
def create_commercial_order(body: OrderIn, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    if body.confirm_now and body.sync_budget:
        admin_service.assert_resource_allowed(db, user, "meu-orcamento")
    if body.confirm_now and body.sync_crm:
        admin_service.assert_resource_allowed(db, user, "dashboard-crm")
    payload = body.model_dump()
    payload["items"] = [i.model_dump() for i in body.items]
    return catalog_service.create_order(db, user, payload)


@catalog_router.post("/orders/{order_id}/confirm")
def confirm_commercial_order(
    order_id: uuid.UUID, body: OrderConfirmIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    if body.sync_budget:
        admin_service.assert_resource_allowed(db, user, "meu-orcamento")
    if body.sync_crm:
        admin_service.assert_resource_allowed(db, user, "dashboard-crm")
    return catalog_service.confirm_order(
        db,
        user,
        order_id,
        sync_budget=body.sync_budget,
        sync_crm=body.sync_crm,
    )


@catalog_router.post("/orders/{order_id}/cancel")
def cancel_commercial_order(
    order_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    return catalog_service.cancel_order(db, user, order_id)


# ---------------------------------------------------------------- Propostas & Documentos PDF


@proposals_router.get("/hub/bridges")
def get_proposals_hub_bridges(user: CurrentUser, db: DbSession) -> dict[str, Any]:
    blocked = admin_service.effective_blocked_resources(db, user)
    bridges = commerce_shared.list_hub_bridges(db, user.id)
    catalog_data = (
        {"items": []}
        if "catalogo" in blocked
        else catalog_service.list_items(db, user.id, active_only=True)
    )
    orders = [] if "catalogo" in blocked else catalog_service.list_orders(db, user.id)[:40]
    return {
        "contacts": [] if "dashboard-crm" in blocked else bridges["contacts"],
        "deals": [] if "dashboard-crm" in blocked else bridges["deals"],
        "chats": [] if "mensageria" in blocked else bridges["chats"],
        "catalog_items": catalog_data["items"],
        "orders": orders,
    }


@proposals_router.get("")
def list_commercial_documents(
    user: CurrentUser,
    db: DbSession,
    doc_type: Annotated[
        Literal["proposal", "service_order", "contract", "receipt"] | None, Query()
    ] = None,
) -> list[dict[str, Any]]:
    return proposals_service.list_documents(db, user.id, doc_type=doc_type)


@proposals_router.post("", status_code=status.HTTP_201_CREATED)
def create_commercial_document(
    body: DocumentIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    payload = body.model_dump()
    payload["items"] = [i.model_dump() for i in body.items]
    return proposals_service.create_document(db, user, payload)


@proposals_router.patch("/{doc_id}")
def patch_commercial_document(
    doc_id: uuid.UUID, body: DocumentPatch, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    changes = body.model_dump(exclude_unset=True)
    if "items" in changes and body.items is not None:
        changes["items"] = [i.model_dump() for i in body.items]
    return proposals_service.update_document(db, user.id, doc_id, changes)


@proposals_router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_commercial_document(doc_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    proposals_service.delete_document(db, user.id, doc_id)


@proposals_router.get("/{doc_id}/pdf")
def download_commercial_document_pdf(
    doc_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> Response:
    pdf_bytes, filename = proposals_service.render_document_pdf(db, user, doc_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@proposals_router.post("/{doc_id}/send-messaging")
def send_document_messaging(
    doc_id: uuid.UUID, body: SendDocumentIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    return proposals_service.send_document_to_messaging(
        db, user, doc_id, body.chat_id, caption=body.caption
    )


@proposals_router.post("/{doc_id}/approve")
def approve_commercial_document(
    doc_id: uuid.UUID, body: ApproveDocumentIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    if body.sync_budget:
        admin_service.assert_resource_allowed(db, user, "meu-orcamento")
    if body.sync_crm:
        admin_service.assert_resource_allowed(db, user, "dashboard-crm")
    return proposals_service.approve_and_sync(
        db, user, doc_id, sync_crm=body.sync_crm, sync_budget=body.sync_budget
    )


@proposals_router.post("/{doc_id}/create-project", status_code=status.HTTP_201_CREATED)
def create_proposal_project(doc_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    from app.services.work.projects import create_project_from_proposal

    return create_project_from_proposal(db, user, doc_id)
