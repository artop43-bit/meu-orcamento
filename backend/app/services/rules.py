"""Regras automáticas de categoria ("descrição contém X → categoria Y")."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import Category, CategoryRule, User
from app.services import budget
from app.services.suggest import normalize


def list_rules(db: Session, user: User) -> list[CategoryRule]:
    return list(
        db.scalars(
            select(CategoryRule)
            .where(CategoryRule.user_id == user.id)
            .order_by(CategoryRule.pattern)
        )
    )


def create_rule(db: Session, user: User, pattern: str, category_id: uuid.UUID) -> CategoryRule:
    """Cria a regra, ou troca a categoria se já existe uma com o mesmo texto."""
    text = normalize(pattern)
    if len(text) < 2:
        raise AppError(400, "invalid_rule", "Use pelo menos 2 letras no texto da regra.")
    budget._owned(db, Category, category_id, user)
    rule = db.scalar(
        select(CategoryRule).where(CategoryRule.user_id == user.id, CategoryRule.pattern == text)
    )
    if rule is None:
        rule = CategoryRule(user_id=user.id, pattern=text[:60], category_id=category_id)
        db.add(rule)
    else:
        rule.category_id = category_id
    db.commit()
    return rule


def delete_rule(db: Session, user: User, rule_id: uuid.UUID) -> None:
    db.delete(budget._owned(db, CategoryRule, rule_id, user))
    db.commit()


def matcher(db: Session, user: User) -> Any:
    """Função descrição → categoria (a regra com o texto mais longo vence)."""
    rules = sorted(list_rules(db, user), key=lambda r: len(r.pattern), reverse=True)

    def match(description: str) -> uuid.UUID | None:
        text = f" {normalize(description)} "
        for rule in rules:
            if f" {rule.pattern} " in text or (len(rule.pattern) >= 4 and rule.pattern in text):
                return rule.category_id
        return None

    return match
