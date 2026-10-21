"""Conciliação com o extrato (v1.4).

Na prévia da importação, cada linha do extrato é casada com um lançamento feito à mão: mesmo
valor e data até 3 dias de distância (cada lançamento casa com uma linha só, a de data mais
próxima). Na gravação, o lançamento casado é marcado como conferido (ganha a referência do
extrato e fica pago) em vez de entrar de novo; reimportar o mesmo extrato também não duplica.
"""

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.months import cycle_date
from app.db.types import utcnow
from app.models import Expense, Income, User

WINDOW = timedelta(days=3)


@dataclass
class Candidate:
    kind: str
    id: uuid.UUID
    description: str
    amount: Decimal
    day: date


def _manual(column: Any) -> Any:
    # Lançado no app (à mão, pela voz, pela foto ou sem internet), não por outra importação.
    return or_(column.is_(None), column.like("app:%"))


def _candidates(db: Session, user: User, start: date, end: date) -> list[Candidate]:
    lo, hi = start - WINDOW, end + WINDOW
    result: list[Candidate] = []
    for e in db.scalars(
        select(Expense).where(
            Expense.user_id == user.id,
            _manual(Expense.import_ref),
            Expense.month >= (lo.replace(day=1) - timedelta(days=31)),
            Expense.month <= hi,
        )
    ):
        day = e.purchase_date or e.due_date
        if day and lo <= day <= hi:
            result.append(Candidate("expense", e.id, e.description, e.amount, day))
    for i in db.scalars(
        select(Income).where(
            Income.user_id == user.id,
            _manual(Income.import_ref),
            Income.month >= (lo.replace(day=1) - timedelta(days=31)),
            Income.month <= hi,
        )
    ):
        day = cycle_date(i.month, i.day, user.month_start_day) if i.day else None
        if day and lo <= day <= hi:
            result.append(Candidate("income", i.id, i.description, i.amount, day))
    return result


def match(db: Session, user: User, items: list[dict[str, Any]]) -> None:
    """Preenche `match` nos itens da prévia (os repetidos de outra importação ficam de fora)."""
    pending = [i for i in items if not i.get("duplicate")]
    if not pending:
        return
    pool = _candidates(db, user, min(i["date"] for i in pending), max(i["date"] for i in pending))
    pairs = []
    for index, item in enumerate(pending):
        for cand in pool:
            if cand.kind == item["kind"] and cand.amount == item["amount"]:
                distance = abs((cand.day - item["date"]).days)
                if distance <= WINDOW.days:
                    pairs.append((distance, index, cand))
    used_items: set[int] = set()
    used_cands: set[uuid.UUID] = set()
    for _, index, cand in sorted(pairs, key=lambda p: p[0]):
        if index in used_items or cand.id in used_cands:
            continue
        used_items.add(index)
        used_cands.add(cand.id)
        pending[index]["match"] = {
            "id": cand.id,
            "kind": cand.kind,
            "description": cand.description,
            "date": cand.day,
        }


def confirm(db: Session, user: User, item: dict[str, Any]) -> bool:
    """Marca o lançamento casado como conferido pelo extrato. Devolve False se não deu."""
    model = Expense if item["kind"] == "expense" else Income
    record = db.get(model, item["match_id"])
    if record is None or record.user_id != user.id:
        return False
    if record.import_ref and not record.import_ref.startswith("app:"):
        return False
    record.import_ref = item["ref"]
    if isinstance(record, Expense):
        if not record.paid:
            record.paid, record.paid_at = True, utcnow()
        record.needs_review = False
    return True
