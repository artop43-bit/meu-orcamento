"""Serviços de Catálogo de Produtos/Serviços, Movimentações de Estoque e Pedidos."""

from __future__ import annotations

import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.money import Q2, Q3, ZERO, to_dec
from app.core.months import current_month, cycle_date, today_local
from app.db.types import utcnow
from app.models import (
    CatalogItem,
    CatalogMovement,
    CommercialDocument,
    CommercialOrder,
    CrmActivity,
    CrmDeal,
    CrmStage,
    Income,
    User,
)
from app.services import budget as budget_service
from app.services.commerce.shared import (
    apply_discount,
    create_budget_income,
    next_sequence,
    resolve_contact_info,
    resolve_line_items,
    sync_won_deal_for_sale,
)
from app.services.common import get_owned, row_lock_guard

ITEM_KINDS = ("product", "service")
MOVEMENT_KINDS = ("in", "out", "adjust")


def serialize_item(item: CatalogItem) -> dict[str, Any]:
    cost = Decimal(item.cost_price or ZERO).quantize(Q2)
    sale = Decimal(item.sale_price or ZERO).quantize(Q2)
    stock = Decimal(item.stock_qty or ZERO).quantize(Q3)
    min_stock = Decimal(item.min_stock or ZERO).quantize(Q3)
    unit_margin = (sale - cost).quantize(Q2, rounding=ROUND_HALF_UP)
    margin_pct = (
        ((unit_margin / sale) * Decimal("100")).quantize(Q2, rounding=ROUND_HALF_UP)
        if sale > ZERO
        else ZERO
    )
    low_stock = item.kind == "product" and bool(item.active) and stock <= min_stock
    return {
        "id": item.id,
        "kind": item.kind,
        "sku": item.sku,
        "name": item.name,
        "unit": item.unit,
        "cost_price": str(cost),
        "sale_price": str(sale),
        "unit_margin": str(unit_margin),
        "margin_pct": str(margin_pct),
        "stock_qty": str(stock),
        "min_stock": str(min_stock),
        "low_stock": low_stock,
        "active": bool(item.active),
        "notes": item.notes,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def list_items(
    db: Session,
    user_id: uuid.UUID,
    *,
    kind: str | None = None,
    q: str | None = None,
    active_only: bool = False,
) -> dict[str, Any]:
    stmt = select(CatalogItem).where(CatalogItem.user_id == user_id)
    if kind in ITEM_KINDS:
        stmt = stmt.where(CatalogItem.kind == kind)
    if active_only:
        stmt = stmt.where(CatalogItem.active.is_(True))
    if q and q.strip():
        needle = f"%{q.strip()}%"
        stmt = stmt.where(or_(CatalogItem.name.ilike(needle), CatalogItem.sku.ilike(needle)))
    rows = list(db.scalars(stmt.order_by(CatalogItem.active.desc(), CatalogItem.name.asc())).all())
    all_rows = (
        rows
        if not (kind or q or active_only)
        else list(db.scalars(select(CatalogItem).where(CatalogItem.user_id == user_id)).all())
    )
    items = [serialize_item(r) for r in rows]
    summary = {
        "total_items": len(all_rows),
        "active_products": sum(1 for r in all_rows if r.kind == "product" and r.active),
        "active_services": sum(1 for r in all_rows if r.kind == "service" and r.active),
        "low_stock_count": sum(
            1 for r in all_rows if r.kind == "product" and r.active and r.stock_qty <= r.min_stock
        ),
        "stock_cost_value": str(
            sum(
                (
                    (Decimal(r.cost_price or ZERO) * Decimal(r.stock_qty or ZERO))
                    for r in all_rows
                    if r.kind == "product" and r.stock_qty > ZERO
                ),
                ZERO,
            ).quantize(Q2)
        ),
        "stock_sale_value": str(
            sum(
                (
                    (Decimal(r.sale_price or ZERO) * Decimal(r.stock_qty or ZERO))
                    for r in all_rows
                    if r.kind == "product" and r.stock_qty > ZERO
                ),
                ZERO,
            ).quantize(Q2)
        ),
    }
    return {"items": items, "summary": summary}


def get_item(db: Session, user_id: uuid.UUID, item_id: uuid.UUID) -> CatalogItem:
    return get_owned(
        db,
        CatalogItem,
        user_id,
        item_id,
        error_code="catalog_item_not_found",
        error_msg="Item do catálogo não encontrado.",
    )


def create_item(db: Session, user_id: uuid.UUID, data: dict[str, Any]) -> dict[str, Any]:
    kind = str(data.get("kind") or "product")
    if kind not in ITEM_KINDS:
        raise AppError(400, "invalid_kind", "Tipo deve ser produto ou serviço.")
    name = str(data.get("name") or "").strip()[:140]
    if not name:
        raise AppError(400, "invalid_name", "Informe o nome do produto ou serviço.")

    cost_price = to_dec(data.get("cost_price", 0), field="custo")
    sale_price = to_dec(data.get("sale_price", 0), field="preço de venda")
    stock_qty = (
        to_dec(data.get("stock_qty", 0), field="estoque inicial", scale=Q3)
        if kind == "product"
        else ZERO
    )
    min_stock = (
        to_dec(data.get("min_stock", 0), field="estoque mínimo", scale=Q3)
        if kind == "product"
        else ZERO
    )

    now = utcnow()
    item = CatalogItem(
        user_id=user_id,
        kind=kind,
        sku=(str(data.get("sku") or "").strip()[:40] or None),
        name=name,
        unit=(
            str(data.get("unit") or ("un" if kind == "product" else "serv")).strip()[:16] or "un"
        ),
        cost_price=cost_price,
        sale_price=sale_price,
        stock_qty=stock_qty,
        min_stock=min_stock,
        active=bool(data.get("active", True)),
        notes=(str(data.get("notes") or "").strip() or None),
        created_at=now,
        updated_at=now,
    )
    db.add(item)
    db.flush()
    if kind == "product" and stock_qty > ZERO:
        db.add(
            CatalogMovement(
                user_id=user_id,
                item_id=item.id,
                kind="in",
                qty=stock_qty,
                reason="Saldo inicial",
                created_at=now,
            )
        )
    db.commit()
    db.refresh(item)
    return serialize_item(item)


def update_item(
    db: Session, user_id: uuid.UUID, item_id: uuid.UUID, changes: dict[str, Any]
) -> dict[str, Any]:
    item = get_item(db, user_id, item_id)
    if "kind" in changes and changes["kind"] in ITEM_KINDS:
        item.kind = str(changes["kind"])
    if "name" in changes and changes["name"] is not None:
        clean = str(changes["name"]).strip()[:140]
        if not clean:
            raise AppError(400, "invalid_name", "Informe o nome do produto ou serviço.")
        item.name = clean
    if "sku" in changes:
        item.sku = str(changes["sku"] or "").strip()[:40] or None
    if "unit" in changes and changes["unit"] is not None:
        item.unit = str(changes["unit"]).strip()[:16] or "un"
    if "cost_price" in changes and changes["cost_price"] is not None:
        item.cost_price = to_dec(changes["cost_price"], field="custo")
    if "sale_price" in changes and changes["sale_price"] is not None:
        item.sale_price = to_dec(changes["sale_price"], field="preço de venda")
    if "min_stock" in changes and changes["min_stock"] is not None:
        item.min_stock = (
            to_dec(changes["min_stock"], field="estoque mínimo", scale=Q3)
            if item.kind == "product"
            else ZERO
        )
    if "active" in changes and changes["active"] is not None:
        item.active = bool(changes["active"])
    if "notes" in changes:
        item.notes = str(changes["notes"] or "").strip() or None
    item.updated_at = utcnow()
    db.commit()
    db.refresh(item)
    return serialize_item(item)


def delete_item(db: Session, user_id: uuid.UUID, item_id: uuid.UUID) -> None:
    item = get_item(db, user_id, item_id)
    db.delete(item)
    db.commit()


def adjust_stock(
    db: Session,
    user_id: uuid.UUID,
    item_id: uuid.UUID,
    *,
    kind: str,
    qty: Any,
    reason: str | None = None,
) -> dict[str, Any]:
    if kind not in MOVEMENT_KINDS:
        raise AppError(400, "invalid_movement_kind", "Tipo de movimentação inválido.")
    item = get_owned(
        db,
        CatalogItem,
        user_id,
        item_id,
        error_code="catalog_item_not_found",
        error_msg="Item do catálogo não encontrado.",
        lock=True,
    )
    if item.kind != "product":
        raise AppError(409, "service_has_no_stock", "Serviços não possuem controle de estoque.")

    val = to_dec(qty, field="quantidade", scale=Q3)
    current = Decimal(item.stock_qty or ZERO).quantize(Q3)
    if kind == "in":
        if val <= ZERO:
            raise AppError(400, "invalid_qty", "Quantidade de entrada deve ser maior que zero.")
        new_stock = to_dec(current + val, field="estoque", scale=Q3)
        logged_qty = val
    elif kind == "out":
        if val <= ZERO:
            raise AppError(400, "invalid_qty", "Quantidade de saída deve ser maior que zero.")
        if current - val < ZERO:
            raise AppError(
                409,
                "insufficient_stock",
                f"Estoque insuficiente para '{item.name}'. Saldo atual: {current}.",
            )
        new_stock = to_dec(current - val, field="estoque", scale=Q3)
        logged_qty = val
    else:
        new_stock = to_dec(val, field="estoque", scale=Q3)
        logged_qty = (new_stock - current).quantize(Q3)

    now = utcnow()
    item.stock_qty = new_stock
    item.updated_at = now
    db.add(
        CatalogMovement(
            user_id=user_id,
            item_id=item.id,
            kind=kind,
            qty=logged_qty,
            reason=(reason or "").strip()[:180] or "Ajuste manual",
            created_at=now,
        )
    )
    db.commit()
    db.refresh(item)
    return serialize_item(item)


def list_movements(
    db: Session, user_id: uuid.UUID, *, item_id: uuid.UUID | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    stmt = select(CatalogMovement).where(CatalogMovement.user_id == user_id)
    if item_id is not None:
        stmt = stmt.where(CatalogMovement.item_id == item_id)
    rows = list(db.scalars(stmt.order_by(CatalogMovement.created_at.desc()).limit(limit)).all())
    item_names = {
        i.id: i.name
        for i in db.scalars(select(CatalogItem).where(CatalogItem.user_id == user_id)).all()
    }
    return [
        {
            "id": m.id,
            "item_id": m.item_id,
            "item_name": item_names.get(m.item_id, "Item"),
            "kind": m.kind,
            "qty": str(Decimal(m.qty or ZERO).quantize(Q3)),
            "reason": m.reason,
            "order_id": m.order_id,
            "created_at": m.created_at,
        }
        for m in rows
    ]


# ---------------------------------------------------------------- pedidos comerciais


def serialize_order(order: CommercialOrder, *, warning: str | None = None) -> dict[str, Any]:
    total = Decimal(order.total_amount or ZERO).quantize(Q2)
    cost = Decimal(order.total_cost or ZERO).quantize(Q2)
    profit = (total - cost).quantize(Q2)
    out: dict[str, Any] = {
        "id": order.id,
        "number": order.number,
        "contact_id": order.contact_id,
        "customer_name": order.customer_name,
        "items": list(order.items_json or []),
        "discount": str(Decimal(order.discount or ZERO).quantize(Q2)),
        "total_amount": str(total),
        "total_cost": str(cost),
        "gross_profit": str(profit),
        "status": order.status,
        "crm_deal_id": order.crm_deal_id,
        "budget_income_id": order.budget_income_id,
        "notes": order.notes,
        "created_at": order.created_at,
        "updated_at": order.updated_at,
    }
    if warning:
        out["warning"] = warning
    return out


def list_orders(db: Session, user_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = list(
        db.scalars(
            select(CommercialOrder)
            .where(CommercialOrder.user_id == user_id)
            .order_by(CommercialOrder.created_at.desc())
            .limit(100)
        ).all()
    )
    return [serialize_order(r) for r in rows]


def get_order(db: Session, user_id: uuid.UUID, order_id: uuid.UUID) -> CommercialOrder:
    return get_owned(
        db,
        CommercialOrder,
        user_id,
        order_id,
        error_code="order_not_found",
        error_msg="Pedido não encontrado.",
    )


def create_order(db: Session, user: User, data: dict[str, Any]) -> dict[str, Any]:
    contact, customer_name = resolve_contact_info(
        db, user.id, data.get("contact_id"), data.get("customer_name")
    )
    items, subtotal, total_cost = resolve_line_items(db, user.id, list(data.get("items") or []))
    discount, total_amount = apply_discount(subtotal, data.get("discount", 0))

    deal_id = data.get("crm_deal_id")
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
    order: CommercialOrder | None = None
    for attempt in range(3):
        candidate = CommercialOrder(
            user_id=user.id,
            number=next_sequence(db, CommercialOrder, user.id),
            contact_id=contact.id if contact else None,
            customer_name=customer_name,
            items_json=items,
            discount=discount,
            total_amount=total_amount,
            total_cost=total_cost,
            status="draft",
            crm_deal_id=deal_id,
            notes=(str(data.get("notes") or "").strip() or None),
            created_at=now,
            updated_at=now,
        )
        try:
            with db.begin_nested():
                db.add(candidate)
                db.flush()
            order = candidate
            break
        except IntegrityError:
            if attempt == 2:
                raise
    assert order is not None
    db.commit()
    db.refresh(order)

    if data.get("confirm_now"):
        return confirm_order(
            db,
            user,
            order.id,
            sync_budget=bool(data.get("sync_budget", False)),
            sync_crm=bool(data.get("sync_crm", False)),
        )
    return serialize_order(order)


def confirm_order(
    db: Session,
    user: User,
    order_id: uuid.UUID,
    *,
    sync_budget: bool = False,
    sync_crm: bool = False,
) -> dict[str, Any]:
    """Confirma o pedido, dá baixa nos produtos em estoque e integra Orçamento/CRM."""
    with row_lock_guard(db):
        return _confirm_order_locked(
            db,
            user,
            order_id,
            sync_budget=sync_budget,
            sync_crm=sync_crm,
        )


def _confirm_order_locked(
    db: Session,
    user: User,
    order_id: uuid.UUID,
    *,
    sync_budget: bool = False,
    sync_crm: bool = False,
) -> dict[str, Any]:
    order = db.scalar(
        select(CommercialOrder)
        .where(CommercialOrder.id == order_id, CommercialOrder.user_id == user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if order is None:
        raise AppError(404, "order_not_found", "Pedido não encontrado.")
    if order.status == "cancelled":
        raise AppError(409, "order_cancelled", "Pedido cancelado não pode ser confirmado.")

    now = utcnow()
    if order.status == "draft":
        product_ids = [
            uuid.UUID(line["item_id"])
            for line in (order.items_json or [])
            if line.get("item_id") and line.get("kind") == "product"
        ]
        locked_items: dict[uuid.UUID, CatalogItem] = {}
        if product_ids:
            for item in db.scalars(
                select(CatalogItem)
                .where(CatalogItem.user_id == user.id, CatalogItem.id.in_(product_ids))
                .with_for_update()
            ).all():
                locked_items[item.id] = item

        # Valida saldo de todos os produtos antes de debitar.
        needed_by_id: dict[uuid.UUID, Decimal] = {}
        for line in order.items_json or []:
            if line.get("item_id") and line.get("kind") == "product":
                cid = uuid.UUID(line["item_id"])
                needed_by_id[cid] = needed_by_id.get(cid, ZERO) + to_dec(
                    line.get("qty", 0), field="quantidade", scale=Q3
                )

        for cid, need in needed_by_id.items():
            item = locked_items.get(cid)
            if item is None:
                continue
            current = Decimal(item.stock_qty or ZERO).quantize(Q3)
            if current - need < ZERO:
                raise AppError(
                    409,
                    "insufficient_stock",
                    f"Estoque insuficiente para '{item.name}'. Saldo: {current}.",
                )

        for cid, need in needed_by_id.items():
            item = locked_items.get(cid)
            if item is None or need <= ZERO:
                continue
            item.stock_qty = to_dec(
                Decimal(item.stock_qty or ZERO) - need, field="estoque", scale=Q3
            )
            item.updated_at = now
            db.add(
                CatalogMovement(
                    user_id=user.id,
                    item_id=item.id,
                    kind="out",
                    qty=need,
                    reason=f"Pedido #{order.number:04d} · {order.customer_name}"[:180],
                    order_id=order.id,
                    created_at=now,
                )
            )
        order.status = "confirmed"

    if sync_budget and Decimal(order.total_amount or ZERO) > ZERO:
        budget_service.ensure_month(db, user, current_month(user.month_start_day), commit=False)
        income = create_budget_income(
            db,
            user,
            description=f"Pedido #{order.number:04d}: {order.customer_name}",
            amount=Decimal(order.total_amount),
            notes="Receita gerada por Catálogo & Pedidos.",
            order=order,
        )
        order.budget_income_id = income.id

    if sync_crm:
        deal = sync_won_deal_for_sale(
            db,
            user.id,
            existing_deal_id=order.crm_deal_id,
            contact_id=order.contact_id,
            title=f"Pedido #{order.number:04d} · {order.customer_name}",
            value=Decimal(order.total_amount or ZERO),
            budget_income_id=order.budget_income_id,
            activity_note=f"Pedido #{order.number:04d} confirmado",
        )
        order.crm_deal_id = deal.id

    order.updated_at = now
    db.commit()
    db.refresh(order)
    return serialize_order(order)


def cancel_order(db: Session, user: User, order_id: uuid.UUID) -> dict[str, Any]:
    order = get_owned(
        db,
        CommercialOrder,
        user.id,
        order_id,
        error_code="order_not_found",
        error_msg="Pedido não encontrado.",
        lock=True,
    )
    if order.status == "cancelled":
        return serialize_order(order)

    now = utcnow()
    if order.status == "confirmed":
        for line in order.items_json or []:
            if line.get("item_id") and line.get("kind") == "product":
                item = db.scalar(
                    select(CatalogItem)
                    .where(
                        CatalogItem.id == uuid.UUID(line["item_id"]),
                        CatalogItem.user_id == user.id,
                    )
                    .with_for_update()
                )
                qty = to_dec(line.get("qty", 0), field="quantidade", scale=Q3)
                if item is not None and qty > ZERO:
                    item.stock_qty = to_dec(
                        Decimal(item.stock_qty or ZERO) + qty, field="estoque", scale=Q3
                    )
                    item.updated_at = now
                    db.add(
                        CatalogMovement(
                            user_id=user.id,
                            item_id=item.id,
                            kind="in",
                            qty=qty,
                            reason=f"Estorno pedido #{order.number:04d}"[:180],
                            order_id=order.id,
                            created_at=now,
                        )
                    )

    linked_docs = list(
        db.scalars(
            select(CommercialDocument)
            .where(CommercialDocument.user_id == user.id, CommercialDocument.order_id == order.id)
            .with_for_update()
        ).all()
    )
    deal: CrmDeal | None = None
    if order.crm_deal_id is not None:
        deal = db.scalar(
            select(CrmDeal)
            .where(CrmDeal.id == order.crm_deal_id, CrmDeal.user_id == user.id)
            .with_for_update()
        )

    warning: str | None = None
    income_id = (
        order.budget_income_id
        or next((d.budget_income_id for d in linked_docs if d.budget_income_id), None)
        or (deal.budget_income_id if deal else None)
    )
    if income_id is not None:
        income = db.scalar(select(Income).where(Income.id == income_id, Income.user_id == user.id))
        if income is not None:
            cur_month = current_month(user.month_start_day)
            today = today_local()
            is_received = income.month < cur_month or (
                income.account_id is not None
                and (
                    income.day is None
                    or cycle_date(cur_month, income.day, user.month_start_day) <= today
                )
            )
            if is_received:
                warning = "A receita já foi marcada como recebida no Meu Orçamento; ajuste por lá."
            else:
                order.budget_income_id = None
                for doc in linked_docs:
                    if doc.budget_income_id == income.id:
                        doc.budget_income_id = None
                if deal is not None and deal.budget_income_id == income.id:
                    deal.budget_income_id = None
                db.delete(income)

    if deal is not None and deal.status == "won":
        stages = list(
            db.scalars(
                select(CrmStage)
                .where(CrmStage.pipeline_id == deal.pipeline_id)
                .order_by(CrmStage.position.asc())
            ).all()
        )
        won_idx = next(
            (i for i, st in enumerate(stages) if st.id == deal.stage_id or st.is_won),
            len(stages),
        )
        prev_stage = next(
            (st for st in reversed(stages[:won_idx]) if not st.is_won and not st.is_lost),
            None,
        ) or next((st for st in reversed(stages) if not st.is_won and not st.is_lost), None)
        if prev_stage is not None:
            deal.stage_id = prev_stage.id
            deal.status = "open"
            deal.closed_at = None
            deal.updated_at = now
            db.add(
                CrmActivity(
                    user_id=user.id,
                    contact_id=deal.contact_id,
                    deal_id=deal.id,
                    kind="note",
                    body=(
                        f"Pedido #{order.number:04d} cancelado · "
                        f"negócio reaberto para '{prev_stage.name}'."
                    ),
                )
            )

    order.status = "cancelled"
    order.updated_at = now
    db.commit()
    db.refresh(order)
    return serialize_order(order, warning=warning)


def native_catalog_dataset(
    db: Session, user_id: uuid.UUID
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """Conjunto tabular vivo do Catálogo para fontes nativas do Dashboard & CRM."""
    rows_db = list(
        db.scalars(
            select(CatalogItem)
            .where(CatalogItem.user_id == user_id)
            .order_by(CatalogItem.name.asc())
        ).all()
    )
    schema = [
        {"name": "nome", "label": "Item", "type": "text"},
        {"name": "tipo", "label": "Tipo", "type": "text"},
        {"name": "custo", "label": "Custo", "type": "currency"},
        {"name": "preco_venda", "label": "Venda", "type": "currency"},
        {"name": "margem", "label": "Margem unit.", "type": "currency"},
        {"name": "estoque", "label": "Estoque", "type": "number"},
        {"name": "estoque_baixo", "label": "Reposição", "type": "boolean"},
    ]
    rows = [
        {
            "nome": r.name,
            "tipo": "Produto" if r.kind == "product" else "Serviço",
            "custo": float(r.cost_price or ZERO),
            "preco_venda": float(r.sale_price or ZERO),
            "margem": float(Decimal(r.sale_price or ZERO) - Decimal(r.cost_price or ZERO)),
            "estoque": float(r.stock_qty or ZERO),
            "estoque_baixo": bool(r.kind == "product" and r.active and r.stock_qty <= r.min_stock),
        }
        for r in rows_db
    ]
    return schema, rows
