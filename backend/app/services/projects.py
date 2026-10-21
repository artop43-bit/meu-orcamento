"""Projetos e etiquetas (v1.4): despesas de categorias diferentes juntas, com teto opcional."""

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import Expense, Project, User
from app.services import budget


def resolve(db: Session, user: User, name: str | None) -> uuid.UUID | None:
    """Nome digitado no formulário: usa o projeto existente (sem diferenciar maiúsculas) ou cria."""
    clean = " ".join((name or "").split())[:40]
    if not clean:
        return None
    found = db.scalar(
        select(Project).where(Project.user_id == user.id, func.lower(Project.name) == clean.lower())
    )
    if found is None:
        found = Project(user_id=user.id, name=clean)
        db.add(found)
        db.flush()
    return found.id


def overview(db: Session, user: User) -> list[dict[str, Any]]:
    totals = dict(
        db.execute(
            select(Expense.project_id, func.sum(Expense.amount))
            .where(Expense.user_id == user.id, Expense.project_id.is_not(None))
            .group_by(Expense.project_id)
        ).all()
    )
    counts = dict(
        db.execute(
            select(Expense.project_id, func.count())
            .where(Expense.user_id == user.id, Expense.project_id.is_not(None))
            .group_by(Expense.project_id)
        ).all()
    )
    rows = []
    for project in db.scalars(
        select(Project).where(Project.user_id == user.id).order_by(Project.created_at.desc())
    ):
        total = Decimal(totals.get(project.id) or 0)
        rows.append(
            {
                "project": project,
                "total": total,
                "count": counts.get(project.id, 0),
                "pct": round(float(total / project.budget * 100), 1) if project.budget else None,
            }
        )
    return rows


def update(db: Session, user: User, project_id: uuid.UUID, changes: dict[str, Any]) -> Project:
    project = budget._owned(db, Project, project_id, user)
    if changes.get("name"):
        clean = " ".join(changes["name"].split())[:40]
        clash = db.scalar(
            select(Project).where(
                Project.user_id == user.id,
                func.lower(Project.name) == clean.lower(),
                Project.id != project.id,
            )
        )
        if clash is not None:
            raise AppError(400, "duplicate_name", "Já existe um projeto com esse nome.")
        project.name = clean
    if "budget" in changes:
        project.budget = changes["budget"]
    db.commit()
    return project


def remove(db: Session, user: User, project_id: uuid.UUID) -> None:
    """Apaga o projeto; as despesas continuam, só sem a etiqueta."""
    project = budget._owned(db, Project, project_id, user)
    for expense in db.scalars(select(Expense).where(Expense.project_id == project.id)):
        expense.project_id = None
    db.delete(project)
    db.commit()
