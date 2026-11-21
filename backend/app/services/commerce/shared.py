"""Helpers compartilhados e pontes com Orçamento, CRM e Mensageria para Catálogo e Propostas."""

from __future__ import annotations

import calendar
import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.money import Q2, Q3, ZERO, brl, to_dec
from app.core.months import current_month, today_local
from app.models import (
    CatalogItem,
    CommercialDocument,
    CommercialOrder,
    CrmActivity,
    CrmContact,
    CrmDeal,
    Income,
    MessagingChat,
    User,
)
from app.services import budget as budget_service
from app.services.common import get_owned
from app.services.crm import crm as crm_service
from app.services.crm.parsing import format_phone_display


def next_sequence(db: Session, model: type[Any], user_id: uuid.UUID, **extra: Any) -> int:
    """Gera o próximo número sequencial por usuário (e tipo opcional)."""
    stmt = select(func.coalesce(func.max(model.number), 0)).where(model.user_id == user_id)
    for attr, val in extra.items():
        stmt = stmt.where(getattr(model, attr) == val)
    current = db.scalar(stmt) or 0
    return int(current) + 1


def resolve_line_items(
    db: Session,
    user_id: uuid.UUID,
    raw_items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], Decimal, Decimal]:
    """Normaliza itens de pedido ou documento e calcula totais de venda e custo."""
    if not raw_items:
        raise AppError(400, "empty_items", "Adicione pelo menos um item.")

    catalog_ids: list[uuid.UUID] = []
    for raw in raw_items:
        cid = raw.get("item_id")
        if cid:
            try:
                catalog_ids.append(cid if isinstance(cid, uuid.UUID) else uuid.UUID(str(cid)))
            except ValueError as exc:
                raise AppError(400, "invalid_item_id", "Item de catálogo inválido.") from exc

    catalog_map: dict[uuid.UUID, CatalogItem] = {}
    if catalog_ids:
        rows = db.scalars(
            select(CatalogItem).where(
                CatalogItem.user_id == user_id,
                CatalogItem.id.in_(catalog_ids),
            )
        ).all()
        catalog_map = {row.id: row for row in rows}
        for cid in catalog_ids:
            if cid not in catalog_map:
                raise AppError(404, "catalog_item_not_found", "Item do catálogo não encontrado.")

    normalized: list[dict[str, Any]] = []
    subtotal = ZERO
    total_cost = ZERO

    for raw in raw_items:
        cid_raw = raw.get("item_id")
        cat_item: CatalogItem | None = None
        if cid_raw:
            cat_item = catalog_map[
                cid_raw if isinstance(cid_raw, uuid.UUID) else uuid.UUID(str(cid_raw))
            ]

        name = str(raw.get("name") or (cat_item.name if cat_item else "")).strip()[:140]
        if not name:
            raise AppError(400, "invalid_item_name", "Informe a descrição de cada item.")

        qty = to_dec(raw.get("qty", 1), field="quantidade", scale=Q3)
        if qty <= ZERO:
            raise AppError(400, "invalid_qty", f"Quantidade de '{name}' deve ser maior que zero.")

        unit = str(raw.get("unit") or (cat_item.unit if cat_item else "un")).strip()[:16] or "un"
        kind = cat_item.kind if cat_item else str(raw.get("kind") or "service")
        if kind not in {"product", "service"}:
            kind = "service"

        if raw.get("unit_price") is not None and raw.get("unit_price") != "":
            unit_price = to_dec(raw.get("unit_price"), field="preço unitário")
        elif cat_item is not None:
            unit_price = Decimal(cat_item.sale_price).quantize(Q2)
        else:
            unit_price = ZERO

        unit_cost = Decimal(cat_item.cost_price).quantize(Q2) if cat_item is not None else ZERO
        line_total = to_dec(
            (qty * unit_price).quantize(Q2, rounding=ROUND_HALF_UP),
            field=f"subtotal de '{name}'",
        )
        line_cost = to_dec(
            (qty * unit_cost).quantize(Q2, rounding=ROUND_HALF_UP),
            field=f"custo de '{name}'",
        )

        subtotal = to_dec(subtotal + line_total, field="subtotal dos itens")
        total_cost = to_dec(total_cost + line_cost, field="custo total dos itens")
        normalized.append(
            {
                "item_id": str(cat_item.id) if cat_item else None,
                "kind": kind,
                "name": name,
                "unit": unit,
                "qty": str(qty),
                "unit_price": str(unit_price),
                "unit_cost": str(unit_cost),
                "total": str(line_total),
            }
        )

    return normalized, subtotal.quantize(Q2), total_cost.quantize(Q2)


def apply_discount(subtotal: Decimal, raw_discount: Any) -> tuple[Decimal, Decimal]:
    discount = to_dec(raw_discount, field="desconto")
    if discount > subtotal:
        raise AppError(400, "invalid_discount", "Desconto não pode superar o subtotal dos itens.")
    total = (subtotal - discount).quantize(Q2, rounding=ROUND_HALF_UP)
    return discount, total


def resolve_contact_info(
    db: Session,
    user_id: uuid.UUID,
    contact_id: uuid.UUID | None,
    customer_name: str | None,
) -> tuple[CrmContact | None, str]:
    contact: CrmContact | None = None
    if contact_id is not None:
        contact = get_owned(
            db,
            CrmContact,
            user_id,
            contact_id,
            error_code="contact_not_found",
            error_msg="Contato do CRM não encontrado.",
        )
    clean_name = (customer_name or (contact.name if contact else "")).strip()[:140]
    if not clean_name:
        raise AppError(400, "missing_customer", "Informe o nome do cliente.")
    return contact, clean_name


def safe_budget_day(target_date: Any, target_month: Any) -> int:
    """Mantém o dia do lançamento dentro do mês calculado (inclusive mês financeiro != dia 1)."""
    last = calendar.monthrange(target_month.year, target_month.month)[1]
    return min(int(target_date.day), last)


def create_budget_income(
    db: Session,
    user: User,
    *,
    description: str,
    amount: Decimal,
    notes: str,
    doc: CommercialDocument | None = None,
    order: CommercialOrder | None = None,
    deal: CrmDeal | None = None,
) -> Income:
    """Registra (ou reaproveita na cadeia documento/pedido/negócio) receita no Orçamento."""
    if doc is not None and order is None and doc.order_id is not None:
        order = db.scalar(
            select(CommercialOrder)
            .where(CommercialOrder.id == doc.order_id, CommercialOrder.user_id == user.id)
            .with_for_update()
        )
    if deal is None:
        deal_id = (doc.crm_deal_id if doc else None) or (order.crm_deal_id if order else None)
        if deal_id is not None:
            deal = db.scalar(
                select(CrmDeal)
                .where(CrmDeal.id == deal_id, CrmDeal.user_id == user.id)
                .with_for_update()
            )

    chain: list[Any] = [obj for obj in (doc, order, deal) if obj is not None]
    existing_income: Income | None = None
    existing_ids = {
        getattr(obj, "budget_income_id", None)
        for obj in chain
        if getattr(obj, "budget_income_id", None) is not None
    }
    if existing_ids:
        existing_income = db.scalar(
            select(Income).where(Income.user_id == user.id, Income.id.in_(existing_ids))
        )
    if existing_income is None and order is not None:
        linked_doc_inc_id = db.scalar(
            select(CommercialDocument.budget_income_id).where(
                CommercialDocument.user_id == user.id,
                CommercialDocument.order_id == order.id,
                CommercialDocument.budget_income_id.is_not(None),
            )
        )
        if linked_doc_inc_id is not None:
            existing_income = db.scalar(
                select(Income).where(Income.user_id == user.id, Income.id == linked_doc_inc_id)
            )

    if existing_income is None:
        clean_amount = to_dec(amount, field="valor da receita")
        if clean_amount <= ZERO:
            raise AppError(
                400, "invalid_amount", "Informe um valor maior que zero para lançar receita."
            )
        target_date = today_local()
        target_month = current_month(user.month_start_day)
        anchor_ref = (
            f"hub-order-{order.id}"
            if order is not None
            else f"hub-doc-{doc.id}"
            if doc is not None
            else f"hub-deal-{deal.id}"
            if deal is not None
            else None
        )
        income_payload: dict[str, Any] = {
            "description": description.strip()[:120],
            "amount": clean_amount,
            "income_type": "variable",
            "day": safe_budget_day(target_date, target_month),
            "notes": notes[:500],
        }
        if anchor_ref is not None:
            income_payload["client_ref"] = anchor_ref
        existing_income = budget_service.create_income(
            db,
            user,
            target_month,
            income_payload,
            commit=False,
        )

    for obj in chain:
        if getattr(obj, "budget_income_id", None) is None:
            obj.budget_income_id = existing_income.id
    db.flush()
    return existing_income


def sync_won_deal_for_sale(
    db: Session,
    user_id: uuid.UUID,
    *,
    existing_deal_id: uuid.UUID | None,
    contact_id: uuid.UUID | None,
    title: str,
    value: Decimal,
    budget_income_id: uuid.UUID | None,
    activity_note: str,
) -> CrmDeal:
    """Cria ou marca como Ganho um negócio no CRM vinculado a venda/proposta."""
    pipeline, stages = crm_service.ensure_default_pipeline(db, user_id)
    won_stage = next((s for s in stages if s.is_won), stages[-1])

    deal: CrmDeal | None = None
    if existing_deal_id is not None:
        deal = db.scalar(
            select(CrmDeal).where(CrmDeal.id == existing_deal_id, CrmDeal.user_id == user_id)
        )
    if deal is None:
        deal = CrmDeal(
            user_id=user_id,
            pipeline_id=pipeline.id,
            stage_id=won_stage.id,
            contact_id=contact_id,
            title=title[:140],
            value=value.quantize(Q2),
            status="won",
            budget_income_id=budget_income_id,
            notes=activity_note,
        )
        db.add(deal)
        db.flush()
    else:
        deal.stage_id = won_stage.id
        deal.status = "won"
        if value > ZERO:
            deal.value = value.quantize(Q2)
        if budget_income_id is not None and deal.budget_income_id is None:
            deal.budget_income_id = budget_income_id

    db.add(
        CrmActivity(
            user_id=user_id,
            contact_id=deal.contact_id or contact_id,
            deal_id=deal.id,
            kind="budget" if budget_income_id else "note",
            body=f"{activity_note} ({brl(value)})",
        )
    )
    db.flush()
    return deal


def list_hub_bridges(db: Session, user_id: uuid.UUID) -> dict[str, Any]:
    """Lista contatos CRM, negócios abertos e chats da Mensageria para os seletores locais."""
    contacts = [
        {
            "id": c.id,
            "name": c.name,
            "phone": c.phone,
            "phone_display": format_phone_display(c.phone) if c.phone else "",
            "email": c.email,
            "messaging_chat_id": c.messaging_chat_id,
        }
        for c in db.scalars(
            select(CrmContact)
            .where(CrmContact.user_id == user_id)
            .order_by(CrmContact.name.asc())
            .limit(120)
        ).all()
    ]
    deals = [
        {
            "id": d.id,
            "title": d.title,
            "value": str(Decimal(d.value or ZERO).quantize(Q2)),
            "status": d.status,
            "contact_id": d.contact_id,
        }
        for d in db.scalars(
            select(CrmDeal)
            .where(CrmDeal.user_id == user_id)
            .order_by(CrmDeal.updated_at.desc())
            .limit(80)
        ).all()
    ]
    chats = [
        {
            "id": ch.id,
            "name": ch.name,
            "phone": ch.phone,
            "phone_display": format_phone_display(ch.phone) if ch.phone else "",
        }
        for ch in db.scalars(
            select(MessagingChat)
            .where(MessagingChat.user_id == user_id, MessagingChat.archived.is_(False))
            .order_by(MessagingChat.last_message_at.desc().nullslast(), MessagingChat.name.asc())
            .limit(120)
        ).all()
    ]
    return {"contacts": contacts, "deals": deals, "chats": chats}
