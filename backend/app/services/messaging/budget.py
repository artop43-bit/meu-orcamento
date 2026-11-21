"""Ponte interna da Mensageria com o Meu Orçamento."""

import calendar
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.months import current_month, format_month, today_local
from app.models import Category, User
from app.services import budget as budget_service
from app.services import cards
from app.services import splits as splits_service
from app.services.messaging.chats import get_chat


def budget_context(
    db: Session,
    user: User,
    *,
    chat_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Lê resumo do Meu Orçamento, categorias, Pix e pessoas em aberto (Divisões/Empréstimos)."""
    month_date = current_month(user.month_start_day)
    month_data = budget_service.get_month(db, user, month_date)

    board = splits_service.board(db, user)
    contacts: list[dict[str, Any]] = []
    for row in board["people"]:
        owes_me = Decimal("0")
        i_owe = Decimal("0")
        open_items = 0
        phone: str | None = None
        for item in row["items"]:
            if item.direction == "owes_me":
                owes_me += item.amount
            else:
                i_owe += item.amount
            open_items += 1
        for loan in row["loans"]:
            if loan.get("settled_at"):
                continue
            if loan.get("phone") and not phone:
                phone = loan["phone"]
            rem = loan["remaining"]
            if loan["direction"] == "owes_me":
                owes_me += rem
            else:
                i_owe += rem
            open_items += 1
        if open_items > 0:
            contacts.append(
                {
                    "person": row["person"],
                    "phone": phone,
                    "owes_me": owes_me,
                    "i_owe": i_owe,
                    "net": owes_me - i_owe,
                    "open_items": open_items,
                }
            )
    contacts.sort(key=lambda r: r["person"].lower())

    linked_contact = None
    if chat_id is not None:
        chat = get_chat(db, user, chat_id)
        target_name = (chat.budget_person or chat.name or "").strip().lower()
        if chat.budget_person:
            linked_contact = next(
                (item for item in contacts if item["person"].lower() == target_name),
                {
                    "person": chat.budget_person,
                    "phone": chat.phone,
                    "owes_me": Decimal("0"),
                    "i_owe": Decimal("0"),
                    "net": Decimal("0"),
                    "open_items": 0,
                },
            )
        elif target_name:
            linked_contact = next(
                (item for item in contacts if item["person"].lower() == target_name),
                None,
            )

    categories = [
        {"id": cat.id, "name": cat.name}
        for cat in db.scalars(
            select(Category).where(Category.user_id == user.id).order_by(Category.name.asc())
        ).all()
    ]

    summary = month_data.summary
    return {
        "month": format_month(month_data.month),
        "income_total": summary["income_total"],
        "expense_total": summary["expense_total"],
        "pending_total": summary["pending_total"],
        "balance": summary["balance"],
        "pix_key": user.pix_key,
        "pix_name": user.pix_name,
        "categories": categories,
        "cards": [{"id": card.id, "name": card.name} for card in cards.credit_cards(db, user)],
        "contacts": contacts,
        "linked_contact": linked_contact,
    }


def create_chat_budget_entry(
    db: Session,
    user: User,
    chat_id: uuid.UUID,
    *,
    kind: str,
    description: str,
    amount: Decimal,
    category_id: uuid.UUID | None = None,
    card_id: uuid.UUID | None = None,
    payment_method: str | None = None,
    paid: bool = True,
    notes: str | None = None,
    client_ref: str | None = None,
) -> dict[str, Any]:
    """Lança uma Receita ou Despesa real no mês atual do Meu Orçamento a partir de uma conversa."""
    chat = get_chat(db, user, chat_id)
    clean_desc = description.strip()[:120]
    if not clean_desc:
        raise AppError(400, "invalid_description", "Informe a descrição do lançamento.")

    month_date = current_month(user.month_start_day)
    budget_service.get_month(db, user, month_date)
    today = today_local()
    clean_notes = (
        notes.strip()[:500] if notes and notes.strip() else f"Via WhatsApp · {chat.name}"
    )[:500]

    if kind == "income":
        safe_day = min(today.day, calendar.monthrange(month_date.year, month_date.month)[1])
        inc = budget_service.create_income(
            db,
            user,
            month_date,
            {
                "description": clean_desc,
                "amount": amount.quantize(Decimal("0.01")),
                "income_type": "variable",
                "day": safe_day,
                "notes": clean_notes,
                **({"client_ref": client_ref} if client_ref else {}),
            },
        )
        return {
            "id": inc.id,
            "kind": "income",
            "month": format_month(month_date),
            "description": inc.description,
            "amount": inc.amount,
        }

    if kind == "expense":
        if payment_method == "credit" and card_id is None:
            raise AppError(
                400, "card_required", "Escolha o cartão de crédito para lançar a compra."
            )
        exp = budget_service.create_expense(
            db,
            user,
            month_date,
            {
                "description": clean_desc,
                "amount": amount.quantize(Decimal("0.01")),
                "category_id": category_id,
                "card_id": card_id,
                "due_date": today,
                "purchase_date": today,
                "paid": paid,
                "payment_method": payment_method or "pix",
                "notes": clean_notes,
                **({"client_ref": client_ref} if client_ref else {}),
            },
        )[0]
        return {
            "id": exp.id,
            "kind": "expense",
            "month": format_month(exp.month),
            "description": exp.description,
            "amount": exp.amount,
        }

    raise AppError(400, "invalid_kind", "Tipo de lançamento inválido.")
