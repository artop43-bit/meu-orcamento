"""Perfil: dados opcionais, foto, banner, resumo pessoal e retrospectiva do mês/ano.

O resumo usa os mesmos números de Insights. O que aparece no perfil é escolha da pessoa
(`profile_prefs`); valores em reais na retrospectiva só aparecem se ela ligar.
"""

import json
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.months import add_months, current_month
from app.models import Category, Expense, Goal, Income, StoredFile, User
from app.services import analysis, budget, files

ZERO = Decimal("0.00")
PROFILE_FIELDS = ("display_name", "bio", "city", "profession")
# Itens do resumo que a pessoa pode mostrar ou ocultar.
STAT_KEYS = (
    "avg_income",
    "avg_expenses",
    "savings_rate",
    "goals_completed",
    "positive_months",
    "best_streak",
    "score",
)
DEFAULT_PREFS: dict[str, Any] = {
    "stats": {key: True for key in STAT_KEYS},
    "show_values_in_recap": False,
}


def prefs(user: User) -> dict[str, Any]:
    result = json.loads(json.dumps(DEFAULT_PREFS))
    if user.profile_prefs:
        try:
            saved = json.loads(user.profile_prefs)
        except ValueError:
            saved = {}
        for key, value in (saved.get("stats") or {}).items():
            if key in STAT_KEYS:
                result["stats"][key] = bool(value)
        if "show_values_in_recap" in saved:
            result["show_values_in_recap"] = bool(saved["show_values_in_recap"])
    return result


def get_profile(db: Session, user: User) -> dict[str, Any]:
    avatar = files.latest(db, user.id, "avatar")
    banner = files.latest(db, user.id, "banner")
    return {
        **{field: getattr(user, field) for field in PROFILE_FIELDS},
        "email": user.email,
        "member_since": user.created_at,
        "avatar_id": avatar.id if avatar else None,
        "banner_id": banner.id if banner else None,
        "prefs": prefs(user),
    }


def update_profile(db: Session, user: User, changes: dict[str, Any]) -> dict[str, Any]:
    for field in PROFILE_FIELDS:
        if field in changes:
            value = changes[field]
            setattr(user, field, value.strip() or None if isinstance(value, str) else None)
    if "prefs" in changes and changes["prefs"] is not None:
        current = prefs(user)
        incoming = changes["prefs"]
        for key, value in (incoming.get("stats") or {}).items():
            if key in STAT_KEYS:
                current["stats"][key] = bool(value)
        if incoming.get("show_values_in_recap") is not None:
            current["show_values_in_recap"] = bool(incoming["show_values_in_recap"])
        user.profile_prefs = json.dumps(current)
    db.commit()
    return get_profile(db, user)


def set_image(db: Session, user: User, purpose: str, raw: bytes) -> dict[str, Any]:
    """Troca a foto ou o banner; a imagem anterior é apagada."""
    previous = list(
        db.scalars(
            select(StoredFile).where(StoredFile.owner_id == user.id, StoredFile.purpose == purpose)
        )
    )
    files.store(db, user, raw, purpose)
    for item in previous:
        db.delete(item)
    db.commit()
    return get_profile(db, user)


def remove_image(db: Session, user: User, purpose: str) -> dict[str, Any]:
    for item in db.scalars(
        select(StoredFile).where(StoredFile.owner_id == user.id, StoredFile.purpose == purpose)
    ):
        db.delete(item)
    db.commit()
    return get_profile(db, user)


# ---------------------------------------------------------------- resumo


def _rate(balance: Decimal, income: Decimal) -> float | None:
    return round(float(balance / income * 100), 1) if income > 0 else None


def _streak(points: list[dict[str, Any]]) -> int:
    best = run = 0
    for point in points:
        if point["has_data"] and point["balance"] > 0:
            run += 1
            best = max(best, run)
        else:
            run = 0
    return best


def summary(db: Session, user: User, today: date | None = None) -> dict[str, Any]:
    """Médias dos últimos 12 meses fechados (ou do mês atual, se ainda não houver histórico)."""
    this_month = current_month() if today is None else today.replace(day=1)
    history = budget.history(db, user, add_months(this_month, -1), 12)
    closed = [p for p in history if p["has_data"]]
    if not closed:
        closed = [p for p in budget.history(db, user, this_month, 1) if p["has_data"]]
    count = len(closed)
    income = sum((p["income"] for p in closed), ZERO)
    expenses = sum((p["expenses"] for p in closed), ZERO)
    goals = list(db.scalars(select(Goal).where(Goal.user_id == user.id)))
    long_history = budget.history(db, user, add_months(this_month, -1), 36)
    score = analysis.score(db, user, this_month)
    return {
        "months": count,
        "avg_income": (income / count).quantize(Decimal("0.01")) if count else None,
        "avg_expenses": (expenses / count).quantize(Decimal("0.01")) if count else None,
        "savings_rate": _rate(income - expenses, income),
        "goals_completed": sum(1 for g in goals if g.current_amount >= g.target_amount),
        "goals_total": len(goals),
        "positive_months": sum(1 for p in long_history if p["has_data"] and p["balance"] > 0),
        "best_streak": _streak(long_history),
        "score": score.get("score"),
        "score_label": score.get("label"),
    }


# ---------------------------------------------------------------- retrospectiva


def _category_totals(db: Session, user: User, start: date, end: date) -> dict[str, Decimal]:
    rows = db.execute(
        select(func.coalesce(Category.name, "Sem categoria"), func.sum(Expense.amount))
        .join(Category, Category.id == Expense.category_id, isouter=True)
        .where(Expense.user_id == user.id, Expense.month.between(start, end))
        .group_by(Category.name)
    )
    return {name: Decimal(total) for name, total in rows}


def retrospective(
    db: Session, user: User, period: str, month: date | None = None, year: int | None = None
) -> dict[str, Any]:
    if period == "month":
        if month is None:
            raise AppError(400, "invalid_period", "Informe o mês.")
        start = end = month
        previous_start = previous_end = add_months(month, -1)
    elif period == "year":
        if year is None:
            raise AppError(400, "invalid_period", "Informe o ano.")
        start, end = date(year, 1, 1), date(year, 12, 1)
        previous_start, previous_end = date(year - 1, 1, 1), date(year - 1, 12, 1)
    else:
        raise AppError(400, "invalid_period", "Período inválido.")

    months = (end.year - start.year) * 12 + end.month - start.month + 1
    points = budget.history(db, user, end, months)
    income = sum((p["income"] for p in points), ZERO)
    expenses = sum((p["expenses"] for p in points), ZERO)
    previous = budget.history(db, user, previous_end, months)
    previous_expenses = sum((p["expenses"] for p in previous), ZERO)

    categories = _category_totals(db, user, start, end)
    previous_categories = _category_totals(db, user, previous_start, previous_end)
    top = max(categories.items(), key=lambda kv: kv[1], default=None)
    savings = sorted(
        (
            (name, previous_categories[name] - categories.get(name, ZERO))
            for name in previous_categories
            if previous_categories[name] - categories.get(name, ZERO) > 0
        ),
        key=lambda kv: kv[1],
        reverse=True,
    )
    with_data = [p for p in points if p["has_data"]]
    best = max(with_data, key=lambda p: p["balance"], default=None)
    entries = (
        db.scalar(
            select(func.count()).where(
                Expense.user_id == user.id, Expense.month.between(start, end)
            )
        )
        or 0
    ) + (
        db.scalar(
            select(func.count()).where(Income.user_id == user.id, Income.month.between(start, end))
        )
        or 0
    )
    goals = list(db.scalars(select(Goal).where(Goal.user_id == user.id)))
    return {
        "period": period,
        "start": start,
        "end": end,
        "has_data": bool(with_data),
        "income": income,
        "expenses": expenses,
        "balance": income - expenses,
        "savings_rate": _rate(income - expenses, income),
        "expenses_change_pct": (
            round(float((expenses - previous_expenses) / previous_expenses * 100), 1)
            if previous_expenses > 0
            else None
        ),
        "top_category": (
            {
                "name": top[0],
                "total": top[1],
                "share_pct": round(float(top[1] / expenses * 100), 1) if expenses > 0 else None,
            }
            if top
            else None
        ),
        "most_saved_category": (
            {"name": savings[0][0], "saved": savings[0][1]} if savings else None
        ),
        "best_month": (
            {"month": best["month"], "balance": best["balance"]}
            if best and period == "year"
            else None
        ),
        "positive_months": sum(1 for p in with_data if p["balance"] > 0),
        "months_with_data": len(with_data),
        "entries": entries,
        "goals_completed": sum(1 for g in goals if g.current_amount >= g.target_amount),
        "show_values": prefs(user)["show_values_in_recap"],
    }


def avatar_map(db: Session, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, uuid.UUID]:
    return files.latest_ids(db, user_ids, "avatar")
