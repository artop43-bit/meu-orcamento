"""Desafios de economia (v1.3): metas curtas de hábito, com progresso pelos próprios lançamentos.

Tipos:
- "no_keyword": nenhum lançamento cuja descrição contenha as palavras (ex.: 30 dias sem delivery);
- "no_category": nenhum gasto na categoria (ex.: semana sem compras por impulso);
- "no_nonessential": nenhum gasto em categorias não essenciais;
- "max_category": gastar no máximo um valor na categoria no período.

A data de cada gasto é a da compra (cartão) ou o vencimento; sem nenhuma das duas, o dia em que
foi lançado. O desafio vence quando o período termina sem falhas e perde na primeira falha.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.months import today_local
from app.db.types import utcnow
from app.models import Category, Challenge, Expense, User
from app.services import budget
from app.services.suggest import normalize

ZERO = Decimal("0")
DELIVERY = "ifood, rappi, delivery, uber eats, aiqfome, ze delivery, james"

TEMPLATES: list[dict[str, Any]] = [
    {
        "key": "delivery",
        "title": "30 dias sem delivery",
        "kind": "no_keyword",
        "keywords": DELIVERY,
        "days": 30,
        "text": "Nenhum pedido de aplicativo de comida por 30 dias.",
    },
    {
        "key": "impulse",
        "title": "Semana sem compras por impulso",
        "kind": "no_category",
        "category": "Compras",
        "days": 7,
        "text": "Nenhum gasto em Compras por 7 dias.",
    },
    {
        "key": "essentials",
        "title": "7 dias só com o essencial",
        "kind": "no_nonessential",
        "days": 7,
        "text": "Só gastos em categorias essenciais (moradia, alimentação, saúde…) por uma semana.",
    },
    {
        "key": "leisure",
        "title": "Lazer com teto no mês",
        "kind": "max_category",
        "category": "Lazer",
        "days": 30,
        "text": "Gastar no máximo um valor em Lazer por 30 dias.",
    },
]


def _spent_on(expense: Expense) -> date:
    return expense.purchase_date or expense.due_date or expense.created_at.date()


def _find_category(db: Session, user: User, name: str) -> Category | None:
    return db.scalar(select(Category).where(Category.user_id == user.id, Category.name == name))


def create(db: Session, user: User, data: dict[str, Any]) -> Challenge:
    template = next((t for t in TEMPLATES if t["key"] == data.get("template")), None)
    if data.get("template") and template is None:
        raise AppError(400, "invalid_template", "Desafio não encontrado.")
    kind = template["kind"] if template else data.get("kind")
    if kind not in ("no_keyword", "no_category", "no_nonessential", "max_category"):
        raise AppError(400, "invalid_kind", "Escolha o tipo do desafio.")
    category_id = data.get("category_id")
    if template and template.get("category") and not category_id:
        found = _find_category(db, user, template["category"])
        if found is None:
            raise AppError(
                400,
                "missing_category",
                f"Este desafio usa a categoria {template['category']}, "
                "que não existe na sua conta.",
            )
        category_id = found.id
    if kind in ("no_category", "max_category"):
        if category_id is None:
            raise AppError(400, "missing_category", "Escolha a categoria do desafio.")
        budget._check_category(db, user, category_id)
    keywords = (template or {}).get("keywords") or data.get("keywords")
    if kind == "no_keyword" and not (keywords or "").strip():
        raise AppError(
            400, "missing_keywords", "Informe as palavras do desafio (ex.: ifood, rappi)."
        )
    max_amount = data.get("max_amount")
    if kind == "max_category" and not max_amount:
        raise AppError(400, "missing_amount", "Informe o valor máximo do desafio.")
    days = int(data.get("days") or (template or {}).get("days") or 30)
    if not 3 <= days <= 90:
        raise AppError(400, "invalid_days", "O desafio dura de 3 a 90 dias.")
    title = (data.get("title") or (template or {}).get("title") or "").strip()
    if not title:
        raise AppError(400, "missing_title", "Dê um nome ao desafio.")
    active = db.scalars(
        select(Challenge).where(Challenge.user_id == user.id, Challenge.finished_at.is_(None))
    ).all()
    if len(active) >= 5:
        raise AppError(400, "too_many", "No máximo 5 desafios ao mesmo tempo.")
    challenge = Challenge(
        user_id=user.id,
        title=title[:80],
        kind=kind,
        category_id=category_id if kind in ("no_category", "max_category") else None,
        keywords=keywords.strip()[:200] if kind == "no_keyword" and keywords else None,
        max_amount=max_amount if kind == "max_category" else None,
        start_date=data.get("start_date") or today_local(),
        days=days,
    )
    db.add(challenge)
    db.commit()
    return challenge


def progress(
    db: Session, user: User, challenge: Challenge, today: date | None = None
) -> dict[str, Any]:
    today = today or today_local()
    end = challenge.start_date + timedelta(days=challenge.days - 1)
    window_end = min(today, end)
    words = [normalize(w) for w in (challenge.keywords or "").split(",") if w.strip()]
    essentials = {
        c.id
        for c in db.scalars(select(Category).where(Category.user_id == user.id))
        if c.is_essential
    }
    candidates = db.scalars(
        select(Expense).where(
            Expense.user_id == user.id,
            Expense.month >= challenge.start_date.replace(day=1) - timedelta(days=62),
        )
    )
    hits: list[Expense] = []
    spent = ZERO
    for expense in candidates:
        when = _spent_on(expense)
        if not challenge.start_date <= when <= window_end:
            continue
        if challenge.kind == "no_keyword":
            text = normalize(expense.description)
            if any(w and w in text for w in words):
                hits.append(expense)
        elif challenge.kind == "no_category":
            if expense.category_id == challenge.category_id:
                hits.append(expense)
        elif challenge.kind == "no_nonessential":
            if expense.category_id not in essentials:
                hits.append(expense)
        elif expense.category_id == challenge.category_id:
            spent += expense.amount
    if challenge.kind == "max_category":
        failed = challenge.max_amount is not None and spent > challenge.max_amount
    else:
        failed = bool(hits)
        spent = sum((e.amount for e in hits), ZERO)
    finished = today > end
    status = "lost" if failed else "won" if finished else "active"
    elapsed = max(0, min(challenge.days, (window_end - challenge.start_date).days + 1))
    return {
        "status": status,
        "end_date": end,
        "elapsed_days": elapsed,
        "spent": spent,
        "slips": [
            {"description": e.description, "amount": e.amount, "date": _spent_on(e)}
            for e in sorted(hits, key=_spent_on)[:5]
        ],
    }


def overview(db: Session, user: User) -> list[dict[str, Any]]:
    """Desafios da pessoa com o progresso; os encerrados ficam registrados (vitórias contam)."""
    rows = []
    for challenge in db.scalars(
        select(Challenge)
        .where(Challenge.user_id == user.id)
        .order_by(Challenge.finished_at.is_not(None), Challenge.start_date.desc())
        .limit(30)
    ):
        data = progress(db, user, challenge)
        if data["status"] != "active" and challenge.finished_at is None:
            challenge.finished_at = utcnow()
            challenge.result = data["status"]
        rows.append({"challenge": challenge, **data})
    db.commit()
    return rows


def remove(db: Session, user: User, challenge_id: uuid.UUID) -> None:
    challenge = budget._owned(db, Challenge, challenge_id, user)
    db.delete(challenge)
    db.commit()
