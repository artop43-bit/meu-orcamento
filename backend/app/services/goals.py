"""Metas com objetivo: tipo, motivação, plano mensal, meta principal, aportes e projeção.

A projeção usa, nesta ordem: o ritmo real (aportes dos últimos 3 meses), o plano mensal
informado e, sem nenhum dos dois, a sobra média dos últimos meses fechados.
"""

import math
import uuid
from datetime import date, timedelta
from decimal import ROUND_DOWN, Decimal
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.months import add_months
from app.db.types import utcnow
from app.models import Goal, GoalContribution, StoredFile, User
from app.services import budget, files

ZERO = Decimal("0.00")
KINDS = (
    "emergency",
    "purchase",
    "travel",
    "health",
    "education",
    "home",
    "vehicle",
    "debt",
    "retirement",
    "other",
)
PACE_DAYS = 90


def _owned(db: Session, user: User, goal_id: uuid.UUID) -> Goal:
    return budget._owned(db, Goal, goal_id, user)


def _set_main(db: Session, user: User, goal: Goal) -> None:
    db.execute(
        update(Goal).where(Goal.user_id == user.id, Goal.id != goal.id).values(is_main=False)
    )
    goal.is_main = True


def _sync_completed(goal: Goal) -> None:
    reached = goal.target_amount > 0 and goal.current_amount >= goal.target_amount
    if reached and goal.completed_at is None:
        goal.completed_at = utcnow()
    elif not reached:
        goal.completed_at = None


def create(db: Session, user: User, data: dict[str, Any]) -> Goal:
    is_main = data.pop("is_main", False)
    goal = Goal(user_id=user.id, **data)
    db.add(goal)
    db.flush()
    has_other = db.scalar(
        select(func.count()).where(Goal.user_id == user.id, Goal.id != goal.id, Goal.is_main)
    )
    if is_main or not has_other:
        _set_main(db, user, goal)
    _sync_completed(goal)
    db.commit()
    return goal


def update_goal(db: Session, user: User, goal_id: uuid.UUID, changes: dict[str, Any]) -> Goal:
    goal = _owned(db, user, goal_id)
    is_main = changes.pop("is_main", None)
    budget._apply(goal, changes)
    if is_main:
        _set_main(db, user, goal)
    elif is_main is False:
        goal.is_main = False
    _sync_completed(goal)
    db.commit()
    return goal


def contribute(db: Session, user: User, goal_id: uuid.UUID, amount: Decimal) -> Goal:
    goal = _owned(db, user, goal_id)
    if amount == 0:
        raise AppError(400, "invalid_amount", "Informe um valor diferente de zero.")
    new_amount = goal.current_amount + amount
    if new_amount < 0:
        raise AppError(400, "invalid_amount", "A retirada é maior que o valor guardado na meta.")
    goal.current_amount = new_amount
    db.add(GoalContribution(goal_id=goal.id, amount=amount))
    _sync_completed(goal)
    db.commit()
    return goal


def set_image(db: Session, user: User, goal_id: uuid.UUID, raw: bytes) -> Goal:
    goal = _owned(db, user, goal_id)
    old = list(db.scalars(select(StoredFile).where(StoredFile.goal_id == goal.id)))
    item = files.store(db, user, raw, "goal")
    item.goal_id = goal.id
    for previous in old:
        db.delete(previous)
    db.commit()
    return goal


def remove_image(db: Session, user: User, goal_id: uuid.UUID) -> Goal:
    goal = _owned(db, user, goal_id)
    for item in db.scalars(select(StoredFile).where(StoredFile.goal_id == goal.id)):
        db.delete(item)
    db.commit()
    return goal


def image_ids(db: Session, goal_ids: list[uuid.UUID]) -> dict[uuid.UUID, uuid.UUID]:
    if not goal_ids:
        return {}
    rows = db.execute(
        select(StoredFile.goal_id, StoredFile.id).where(StoredFile.goal_id.in_(goal_ids))
    )
    return {goal_id: file_id for goal_id, file_id in rows}


# ---------------------------------------------------------------- projeção


def _months_between(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + end.month - start.month


def _recent_pace(db: Session, goal: Goal, today: date) -> Decimal:
    """Média mensal guardada nos últimos 3 meses (retiradas descontadas)."""
    since = today - timedelta(days=PACE_DAYS)
    total = db.scalar(
        select(func.coalesce(func.sum(GoalContribution.amount), 0)).where(
            GoalContribution.goal_id == goal.id,
            func.date(GoalContribution.created_at) >= since,
        )
    )
    total = Decimal(total or 0)
    # Meta criada há menos de 3 meses: divide pelos meses de vida dela (mínimo 1).
    age_months = max(1, min(3, math.ceil((today - goal.created_at.date()).days / 30)))
    return (total / age_months).quantize(Decimal("0.01"), rounding=ROUND_DOWN)


def _average_surplus(db: Session, user: User, today: date) -> Decimal:
    history = budget.history(db, user, add_months(today.replace(day=1), -1), 3)
    closed = [p for p in history if p["has_data"]]
    if not closed:
        return ZERO
    avg = sum((p["balance"] for p in closed), ZERO) / len(closed)
    return max(ZERO, avg.quantize(Decimal("0.01"), rounding=ROUND_DOWN))


def projection(db: Session, user: User, goal: Goal, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    remaining = goal.target_amount - goal.current_amount
    base: dict[str, Any] = {
        "remaining": max(ZERO, remaining),
        "pace": None,
        "pace_source": None,
        "eta": None,
        "months_needed": None,
        "required_monthly": None,
        "months_left": None,
    }
    if goal.completed_at is not None or remaining <= 0:
        return {**base, "status": "completed"}

    pace = _recent_pace(db, goal, today)
    source = "contributions"
    if pace <= 0 and goal.monthly_plan:
        pace, source = goal.monthly_plan, "plan"
    if pace <= 0:
        pace, source = _average_surplus(db, user, today), "surplus"

    this_month = today.replace(day=1)
    if goal.target_date:
        months_left = max(1, _months_between(this_month, goal.target_date.replace(day=1)))
        base["months_left"] = months_left
        base["required_monthly"] = (remaining / months_left).quantize(Decimal("0.01"))
    if pace <= 0:
        return {**base, "status": "no_pace"}

    months_needed = math.ceil(remaining / pace)
    eta = add_months(this_month, months_needed)
    base.update(pace=pace, pace_source=source, months_needed=months_needed, eta=eta)
    if goal.target_date is None:
        return {**base, "status": "estimate"}
    target_month = goal.target_date.replace(day=1)
    if eta < target_month and _months_between(eta, target_month) >= 1:
        status = "ahead"
    elif eta <= target_month:
        status = "on_track"
    else:
        status = "behind"
    return {**base, "status": status}


def suggestion(db: Session, user: User, today: date | None = None) -> dict[str, Any] | None:
    """Sobra prevista no mês + meta principal em aberto: sugere destinar parte (nunca sozinho)."""
    month = budget.current_month() if today is None else today.replace(day=1)
    goal = db.scalar(
        select(Goal)
        .where(Goal.user_id == user.id, Goal.completed_at.is_(None))
        .order_by(Goal.is_main.desc(), Goal.created_at)
        .limit(1)
    )
    if goal is None:
        return None
    balance = budget.get_month(db, user, month).summary["balance"]
    already = db.scalar(
        select(func.coalesce(func.sum(GoalContribution.amount), 0))
        .join(Goal, Goal.id == GoalContribution.goal_id)
        .where(Goal.user_id == user.id, func.date(GoalContribution.created_at) >= month)
    )
    free = Decimal(balance) - Decimal(already or 0)
    if free < Decimal("50"):
        return None
    remaining = goal.target_amount - goal.current_amount
    # Metade da sobra, arredondada para baixo em dezenas; nunca mais do que falta na meta.
    amount = min(remaining, (free / 2 / 10).to_integral_value(rounding=ROUND_DOWN) * 10)
    if amount <= 0:
        return None
    return {"goal_id": goal.id, "goal_name": goal.name, "surplus": free, "amount": amount}
