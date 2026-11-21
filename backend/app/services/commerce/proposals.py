"""Serviços de Propostas, Ordens de Serviço, Contratos e Recibos em PDF com envio via WhatsApp."""

from __future__ import annotations

import re
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.money import Q2, ZERO
from app.core.months import current_month
from app.db.types import utcnow
from app.models import (
    CommercialDocument,
    CommercialOrder,
    CrmActivity,
    CrmContact,
    CrmDeal,
    User,
)
from app.services import admin as admin_service
from app.services import budget as budget_service
from app.services.commerce.pdf_doc import DOC_TYPE_TITLES, build_commercial_pdf
from app.services.commerce.shared import (
    apply_discount,
    create_budget_income,
    next_sequence,
    resolve_contact_info,
    resolve_line_items,
    sync_won_deal_for_sale,
)
from app.services.common import get_owned, row_lock_guard
from app.services.messaging import messages as messaging_messages

DOC_TYPES = ("proposal", "service_order", "contract", "receipt")
DOC_STATUSES = ("draft", "sent", "approved", "rejected", "cancelled")


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-").lower()
    return cleaned[:48] or "documento"


def serialize_document(doc: CommercialDocument) -> dict[str, Any]:
    return {
        "id": doc.id,
        "doc_type": doc.doc_type,
        "doc_label": DOC_TYPE_TITLES.get(doc.doc_type, "Documento"),
        "number": doc.number,
        "title": doc.title,
        "contact_id": doc.contact_id,
        "crm_deal_id": doc.crm_deal_id,
        "order_id": doc.order_id,
        "customer_name": doc.customer_name,
        "customer_doc": doc.customer_doc,
        "customer_contact": doc.customer_contact,
        "items": list(doc.items_json or []),
        "discount": str(Decimal(doc.discount or ZERO).quantize(Q2)),
        "total_amount": str(Decimal(doc.total_amount or ZERO).quantize(Q2)),
        "valid_until": doc.valid_until,
        "terms_text": doc.terms_text,
        "status": doc.status,
        "budget_income_id": doc.budget_income_id,
        "created_at": doc.created_at,
        "updated_at": doc.updated_at,
    }


def list_documents(
    db: Session,
    user_id: uuid.UUID,
    *,
    doc_type: str | None = None,
) -> list[dict[str, Any]]:
    stmt = select(CommercialDocument).where(CommercialDocument.user_id == user_id)
    if doc_type in DOC_TYPES:
        stmt = stmt.where(CommercialDocument.doc_type == doc_type)
    rows = list(db.scalars(stmt.order_by(CommercialDocument.created_at.desc()).limit(100)).all())
    return [serialize_document(r) for r in rows]


def get_document(db: Session, user_id: uuid.UUID, doc_id: uuid.UUID) -> CommercialDocument:
    return get_owned(
        db,
        CommercialDocument,
        user_id,
        doc_id,
        error_code="document_not_found",
        error_msg="Documento comercial não encontrado.",
    )


def create_document(db: Session, user: User, data: dict[str, Any]) -> dict[str, Any]:
    doc_type = str(data.get("doc_type") or "proposal")
    if doc_type not in DOC_TYPES:
        raise AppError(400, "invalid_doc_type", "Tipo de documento inválido.")

    order: CommercialOrder | None = None
    if data.get("order_id") is not None:
        order = get_owned(
            db,
            CommercialOrder,
            user.id,
            data["order_id"],
            error_code="order_not_found",
            error_msg="Pedido de origem não encontrado.",
        )

    contact_id = data.get("contact_id") or (order.contact_id if order else None)
    raw_customer_name = data.get("customer_name") or (order.customer_name if order else None)
    contact, customer_name = resolve_contact_info(db, user.id, contact_id, raw_customer_name)

    raw_items = list(data.get("items") or (order.items_json if order else []))
    items, subtotal, _ = resolve_line_items(db, user.id, raw_items)
    raw_discount = (
        data["discount"]
        if data.get("discount") is not None
        else (order.discount if order else ZERO)
    )
    discount, total_amount = apply_discount(subtotal, raw_discount)

    deal_id = data.get("crm_deal_id") or (order.crm_deal_id if order else None)
    if deal_id is not None:
        get_owned(
            db,
            CrmDeal,
            user.id,
            deal_id,
            error_code="deal_not_found",
            error_msg="Negócio do CRM não encontrado.",
        )

    now = utcnow()
    custom_title = str(data.get("title") or "").strip()[:160]
    customer_contact = str(data.get("customer_contact") or "").strip()[:120] or (
        contact.phone or contact.email if contact else None
    )
    doc: CommercialDocument | None = None
    for attempt in range(3):
        number = next_sequence(db, CommercialDocument, user.id, doc_type=doc_type)
        title = (
            custom_title
            or f"{DOC_TYPE_TITLES[doc_type].title()} #{number:04d} · {customer_name}"[:160]
        )
        candidate = CommercialDocument(
            user_id=user.id,
            doc_type=doc_type,
            number=number,
            title=title,
            contact_id=contact.id if contact else None,
            crm_deal_id=deal_id,
            order_id=order.id if order else None,
            customer_name=customer_name,
            customer_doc=(str(data.get("customer_doc") or "").strip()[:40] or None),
            customer_contact=customer_contact,
            items_json=items,
            discount=discount,
            total_amount=total_amount,
            valid_until=data.get("valid_until"),
            terms_text=(str(data.get("terms_text") or "").strip() or None),
            status="draft",
            budget_income_id=order.budget_income_id if order else None,
            created_at=now,
            updated_at=now,
        )
        try:
            with db.begin_nested():
                db.add(candidate)
                db.flush()
            doc = candidate
            break
        except IntegrityError:
            if attempt == 2:
                raise
    assert doc is not None
    db.commit()
    db.refresh(doc)
    return serialize_document(doc)


def update_document(
    db: Session, user_id: uuid.UUID, doc_id: uuid.UUID, changes: dict[str, Any]
) -> dict[str, Any]:
    doc = get_document(db, user_id, doc_id)
    if "title" in changes and changes["title"] is not None:
        clean = str(changes["title"]).strip()[:160]
        if not clean:
            raise AppError(400, "invalid_title", "Informe o título do documento.")
        doc.title = clean
    if "customer_doc" in changes:
        doc.customer_doc = str(changes["customer_doc"] or "").strip()[:40] or None
    if "customer_contact" in changes:
        doc.customer_contact = str(changes["customer_contact"] or "").strip()[:120] or None
    if "valid_until" in changes:
        doc.valid_until = changes["valid_until"]
    if "terms_text" in changes:
        doc.terms_text = str(changes["terms_text"] or "").strip() or None
    if "status" in changes and changes["status"] in DOC_STATUSES:
        doc.status = str(changes["status"])
    if "items" in changes and changes["items"] is not None:
        items, subtotal, _ = resolve_line_items(db, user_id, list(changes["items"]))
        discount, total_amount = apply_discount(
            subtotal,
            changes["discount"] if "discount" in changes else doc.discount,
        )
        doc.items_json = items
        doc.discount = discount
        doc.total_amount = total_amount
    elif "discount" in changes and changes["discount"] is not None:
        subtotal = sum(Decimal(str(i.get("total", 0))) for i in (doc.items_json or []))
        discount, total_amount = apply_discount(subtotal.quantize(Q2), changes["discount"])
        doc.discount = discount
        doc.total_amount = total_amount

    doc.updated_at = utcnow()
    db.commit()
    db.refresh(doc)
    return serialize_document(doc)


def delete_document(db: Session, user_id: uuid.UUID, doc_id: uuid.UUID) -> None:
    doc = get_document(db, user_id, doc_id)
    db.delete(doc)
    db.commit()


def render_document_pdf(db: Session, user: User, doc_id: uuid.UUID) -> tuple[bytes, str]:
    doc = get_document(db, user.id, doc_id)
    pdf_bytes = build_commercial_pdf(
        doc_type=doc.doc_type,
        number=doc.number,
        title=doc.title,
        status=doc.status,
        emitter_name=user.display_name or user.email,
        emitter_email=user.email,
        customer_name=doc.customer_name,
        customer_doc=doc.customer_doc,
        customer_contact=doc.customer_contact,
        items=list(doc.items_json or []),
        discount=Decimal(doc.discount or ZERO),
        total_amount=Decimal(doc.total_amount or ZERO),
        valid_until=doc.valid_until,
        terms_text=doc.terms_text,
        created_at=doc.created_at,
    )
    prefix = {
        "proposal": "proposta",
        "service_order": "os",
        "contract": "contrato",
        "receipt": "recibo",
    }.get(doc.doc_type, "documento")
    filename = f"{prefix}-{doc.number:04d}-{_slug(doc.customer_name)}.pdf"
    return pdf_bytes, filename


def send_document_to_messaging(
    db: Session,
    user: User,
    doc_id: uuid.UUID,
    chat_id: uuid.UUID,
    *,
    caption: str | None = None,
) -> dict[str, Any]:
    """Gera o PDF local e envia diretamente na fila de uma conversa da Mensageria."""
    admin_service.assert_resource_allowed(db, user, "mensageria")
    doc = get_document(db, user.id, doc_id)
    pdf_bytes, filename = render_document_pdf(db, user, doc.id)
    default_caption = (
        f"{DOC_TYPE_TITLES.get(doc.doc_type, 'Documento')} #{doc.number:04d} · {doc.title}"
    )
    msg = messaging_messages.send_media_message(
        db,
        user,
        chat_id,
        data=pdf_bytes,
        mime_type="application/pdf",
        file_name=filename,
        caption=(caption or default_caption)[:4000],
        kind="document",
    )
    if doc.status == "draft":
        doc.status = "sent"
        doc.updated_at = utcnow()
    if doc.contact_id is not None:
        contact = db.scalar(
            select(CrmContact).where(CrmContact.id == doc.contact_id, CrmContact.user_id == user.id)
        )
        if contact is not None:
            db.add(
                CrmActivity(
                    user_id=user.id,
                    contact_id=contact.id,
                    deal_id=doc.crm_deal_id,
                    kind="message",
                    body=f"PDF '{filename}' enviado via Mensageria.",
                )
            )
    db.commit()
    return {"document": serialize_document(doc), "message": msg}


def approve_and_sync(
    db: Session,
    user: User,
    doc_id: uuid.UUID,
    *,
    sync_crm: bool = True,
    sync_budget: bool = True,
) -> dict[str, Any]:
    """Marca o documento como aprovado e integra (idempotente) com Meu Orçamento e CRM."""
    with row_lock_guard(db):
        return _approve_and_sync_locked(
            db,
            user,
            doc_id,
            sync_crm=sync_crm,
            sync_budget=sync_budget,
        )


def _approve_and_sync_locked(
    db: Session,
    user: User,
    doc_id: uuid.UUID,
    *,
    sync_crm: bool = True,
    sync_budget: bool = True,
) -> dict[str, Any]:
    doc = db.scalar(
        select(CommercialDocument)
        .where(CommercialDocument.id == doc_id, CommercialDocument.user_id == user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if doc is None:
        raise AppError(404, "document_not_found", "Documento comercial não encontrado.")
    if doc.status == "cancelled":
        raise AppError(409, "document_cancelled", "Documento cancelado não pode ser aprovado.")

    now = utcnow()
    doc.status = "approved"

    if sync_budget and Decimal(doc.total_amount or ZERO) > ZERO:
        budget_service.ensure_month(db, user, current_month(user.month_start_day), commit=False)
        doc_title = DOC_TYPE_TITLES.get(doc.doc_type, "Proposta").title()
        income = create_budget_income(
            db,
            user,
            description=f"{doc_title} #{doc.number:04d}: {doc.customer_name}",
            amount=Decimal(doc.total_amount),
            notes="Receita gerada por Propostas & Documentos.",
            doc=doc,
        )
        doc.budget_income_id = income.id

    if sync_crm:
        note_prefix = DOC_TYPE_TITLES.get(doc.doc_type, "Documento")
        deal = sync_won_deal_for_sale(
            db,
            user.id,
            existing_deal_id=doc.crm_deal_id,
            contact_id=doc.contact_id,
            title=doc.title,
            value=Decimal(doc.total_amount or ZERO),
            budget_income_id=doc.budget_income_id,
            activity_note=f"{note_prefix} #{doc.number:04d} aprovado",
        )
        doc.crm_deal_id = deal.id

    doc.updated_at = now
    db.commit()
    db.refresh(doc)
    return serialize_document(doc)
