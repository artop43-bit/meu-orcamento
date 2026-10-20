"""Comprovantes de despesa: foto do recibo, da nota ou do boleto pago (só o dono vê)."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import Expense, StoredFile, User
from app.services import budget, files

MAX_PER_EXPENSE = 3


def ids_for(db: Session, expense_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[uuid.UUID]]:
    if not expense_ids:
        return {}
    result: dict[uuid.UUID, list[uuid.UUID]] = {}
    for expense_id, file_id in db.execute(
        select(StoredFile.expense_id, StoredFile.id)
        .where(StoredFile.expense_id.in_(expense_ids))
        .order_by(StoredFile.created_at)
    ):
        result.setdefault(expense_id, []).append(file_id)
    return result


def add(db: Session, user: User, expense_id: uuid.UUID, uploads: list[bytes]) -> list[uuid.UUID]:
    expense = budget._owned(db, Expense, expense_id, user)
    existing = db.scalar(select(func.count()).where(StoredFile.expense_id == expense.id)) or 0
    if not uploads:
        raise AppError(400, "empty_file", "Escolha ao menos uma imagem.")
    if existing + len(uploads) > MAX_PER_EXPENSE:
        raise AppError(
            400,
            "too_many_files",
            f"Cada despesa aceita até {MAX_PER_EXPENSE} comprovantes.",
        )
    for raw in uploads:
        item = files.store(db, user, raw, "receipt")
        item.expense_id = expense.id
    db.commit()
    return ids_for(db, [expense.id]).get(expense.id, [])


def remove(db: Session, user: User, expense_id: uuid.UUID, file_id: uuid.UUID) -> None:
    expense = budget._owned(db, Expense, expense_id, user)
    item = db.get(StoredFile, file_id)
    if item is None or item.expense_id != expense.id:
        raise AppError(404, "not_found", "Comprovante não encontrado.")
    db.delete(item)
    db.commit()
