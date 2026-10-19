"""Cartões (crédito e/ou débito) e faturas.

Cartão de débito não tem fatura nem limite: a compra entra paga e sai da conta vinculada.

Regra da fatura: compras até a véspera do fechamento entram na fatura que fecha naquele mês;
a partir do dia do fechamento vão para a próxima. A conta fica no mês do VENCIMENTO da
fatura (é quando o dinheiro sai), guardando o dia da compra.
Pagar a fatura marca as compras dela como pagas: nada é lançado duas vezes.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.months import add_months, with_day
from app.db.types import utcnow
from app.models import CreditCard, Expense, User
from app.services import budget

ZERO = Decimal("0.00")


def invoice_dates(card: CreditCard, purchase: date) -> tuple[date, date]:
    """(fechamento, vencimento) da fatura em que cai uma compra feita em `purchase`."""
    month = purchase.replace(day=1)
    closing = with_day(month, card.closing_day)
    if purchase >= closing:
        closing = with_day(add_months(month, 1), card.closing_day)
    due_month = closing.replace(day=1)
    if card.due_day <= card.closing_day:
        due_month = add_months(due_month, 1)
    return closing, with_day(due_month, card.due_day)


def installment_dates(card: CreditCard, purchase: date, count: int) -> list[date]:
    """Vencimentos das faturas de cada parcela (uma por mês, a partir da 1ª fatura)."""
    _, first_due = invoice_dates(card, purchase)
    first = first_due.replace(day=1)
    return [with_day(add_months(first, i), card.due_day) for i in range(count)]


def closing_for_due(card: CreditCard, due_month: date) -> date:
    closing_month = due_month if card.due_day > card.closing_day else add_months(due_month, -1)
    return with_day(closing_month, card.closing_day)


# ---------------------------------------------------------------- CRUD


CREDIT_KINDS = ("credit", "both")
DEBIT_KINDS = ("debit", "both")


def has_credit(card: CreditCard) -> bool:
    return card.kind in CREDIT_KINDS


def has_debit(card: CreditCard) -> bool:
    return card.kind in DEBIT_KINDS


def _normalize(card: CreditCard) -> None:
    """Crédito exige fechamento e vencimento; cartão só de débito não guarda dados de fatura."""
    if has_credit(card):
        if card.closing_day is None or card.due_day is None:
            raise AppError(
                400,
                "card_days_required",
                "Informe o dia do fechamento e o dia do vencimento da fatura.",
            )
    else:
        card.closing_day = None
        card.due_day = None
        card.limit_amount = None


def credit_cards(db: Session, user: User) -> list[CreditCard]:
    return [c for c in list_cards(db, user) if has_credit(c)]


def list_cards(db: Session, user: User) -> list[CreditCard]:
    return list(
        db.scalars(
            select(CreditCard).where(CreditCard.user_id == user.id).order_by(CreditCard.name)
        )
    )


def get_card(db: Session, user: User, card_id: uuid.UUID) -> CreditCard:
    return budget._owned(db, CreditCard, card_id, user)


def get_credit_card(db: Session, user: User, card_id: uuid.UUID) -> CreditCard:
    card = get_card(db, user, card_id)
    if not has_credit(card):
        raise AppError(400, "card_not_credit", "Este cartão não tem a função crédito.")
    return card


def get_debit_card(db: Session, user: User, card_id: uuid.UUID) -> CreditCard:
    card = get_card(db, user, card_id)
    if not has_debit(card):
        raise AppError(400, "card_not_debit", "Este cartão não tem a função débito.")
    return card


def create_card(db: Session, user: User, data: dict[str, Any]) -> CreditCard:
    budget._check_account(db, user, data.get("account_id"))
    card = CreditCard(user_id=user.id, **data)
    _normalize(card)
    db.add(card)
    db.commit()
    return card


def update_card(db: Session, user: User, card_id: uuid.UUID, changes: dict[str, Any]) -> CreditCard:
    card = get_card(db, user, card_id)
    budget._check_account(db, user, changes.get("account_id"))
    had_credit = has_credit(card)
    budget._apply(card, changes)
    _normalize(card)
    if had_credit and not has_credit(card):
        pending = db.scalar(
            select(func.count()).where(Expense.card_id == card.id, Expense.paid.is_(False))
        )
        if pending:
            raise AppError(
                400,
                "card_has_invoices",
                "Este cartão tem faturas em aberto. Pague-as antes de remover a função crédito.",
            )
    db.commit()
    return card


def delete_card(db: Session, user: User, card_id: uuid.UUID) -> None:
    """Exclui o cartão; as compras continuam no orçamento, só sem o vínculo."""
    card = get_card(db, user, card_id)
    for expense in db.scalars(select(Expense).where(Expense.card_id == card.id)):
        expense.card_id = None
    for expense in db.scalars(select(Expense).where(Expense.debit_card_id == card.id)):
        expense.debit_card_id = None
    db.delete(card)
    db.commit()


# ---------------------------------------------------------------- resumo e faturas


def _invoice_total(db: Session, card: CreditCard, month: date) -> tuple[Decimal, Decimal, int]:
    """(total, pago, quantidade) da fatura que vence no mês."""
    rows = db.execute(
        select(Expense.paid, func.sum(Expense.amount), func.count())
        .where(Expense.card_id == card.id, Expense.month == month)
        .group_by(Expense.paid)
    ).all()
    total = sum((Decimal(t) for _, t, _ in rows), ZERO)
    paid = sum((Decimal(t) for p, t, _ in rows if p), ZERO)
    count = sum(c for _, _, c in rows)
    return total, paid, count


def invoice(db: Session, card: CreditCard, month: date, today: date) -> dict[str, Any]:
    total, paid, count = _invoice_total(db, card, month)
    closing = closing_for_due(card, month)
    due = with_day(month, card.due_day)
    if count and paid == total:
        status = "paid"
    elif today < closing:
        status = "open"
    elif today > due:
        status = "overdue"
    else:
        status = "closed"
    return {
        "month": month,
        "closing_date": closing,
        "due_date": due,
        "total": total,
        "paid_total": paid,
        "count": count,
        "status": status,
    }


def summary(db: Session, user: User, today: date | None = None) -> list[dict[str, Any]]:
    today = today or date.today()
    result = []
    for card in list_cards(db, user):
        if not has_credit(card):
            result.append(
                {
                    "card": card,
                    "used": ZERO,
                    "available": None,
                    "used_pct": None,
                    "best_day": None,
                    "open_invoice": None,
                    "closed_invoice": None,
                }
            )
            continue
        used = db.scalar(
            select(func.coalesce(func.sum(Expense.amount), 0)).where(
                Expense.card_id == card.id, Expense.paid.is_(False)
            )
        )
        used = Decimal(used or 0).quantize(Decimal("0.01"))
        _, open_due = invoice_dates(card, today)
        current = invoice(db, card, open_due.replace(day=1), today)
        previous = invoice(db, card, add_months(open_due.replace(day=1), -1), today)
        result.append(
            {
                "card": card,
                "used": used,
                "available": (card.limit_amount - used) if card.limit_amount else None,
                "used_pct": (
                    round(float(used / card.limit_amount * 100), 1) if card.limit_amount else None
                ),
                # Comprar no dia do fechamento joga a compra para a fatura seguinte (mais prazo).
                "best_day": card.closing_day,
                "open_invoice": current,
                "closed_invoice": previous if previous["count"] else None,
            }
        )
    return result


def invoices(
    db: Session, user: User, card_id: uuid.UUID, today: date | None = None
) -> list[dict[str, Any]]:
    """Faturas de 3 meses atrás a 6 meses à frente (as futuras têm as parcelas)."""
    today = today or date.today()
    card = get_credit_card(db, user, card_id)
    _, open_due = invoice_dates(card, today)
    base = open_due.replace(day=1)
    return [invoice(db, card, add_months(base, offset), today) for offset in range(-3, 7)]


def invoice_items(db: Session, user: User, card_id: uuid.UUID, month: date) -> list[Expense]:
    card = get_credit_card(db, user, card_id)
    return list(
        db.scalars(
            select(Expense)
            .where(Expense.card_id == card.id, Expense.month == month)
            .order_by(Expense.purchase_date, Expense.created_at)
        )
    )


def pay_invoice(db: Session, user: User, card_id: uuid.UUID, month: date, paid: bool) -> int:
    count = 0
    for expense in invoice_items(db, user, card_id, month):
        if expense.paid != paid:
            expense.paid = paid
            expense.paid_at = utcnow() if paid else None
            count += 1
    db.commit()
    return count


def calendar_events(db: Session, user: User, month: date, today: date) -> list[dict[str, Any]]:
    """Fechamento e vencimento das faturas no mês (para o Calendário)."""
    events = []
    for card in credit_cards(db, user):
        data = invoice(db, card, month, today)
        if not data["count"]:
            continue
        events.append(
            {
                "id": card.id,
                "date": data["due_date"],
                "kind": "invoice",
                "description": f"Fatura {card.name}",
                "amount": data["total"],
                "paid": data["status"] == "paid",
                "category_id": None,
                "category": None,
                "color": card.color,
            }
        )
        # Fechamento que acontece neste mês (pode ser de uma fatura que vence no próximo).
        next_due = add_months(month, 1)
        for due_month in (month, next_due):
            closing = closing_for_due(card, due_month)
            if closing.replace(day=1) == month:
                total, _, count = _invoice_total(db, card, due_month)
                if not count:
                    continue
                events.append(
                    {
                        "id": card.id,
                        "date": closing,
                        "kind": "invoice_close",
                        "description": f"Fecha a fatura {card.name}",
                        "amount": total,
                        "paid": None,
                        "category_id": None,
                        "category": None,
                        "color": card.color,
                    }
                )
    return events
