import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Investment, User
from app.services.budget import _owned

ZERO = Decimal("0.00")


def list_investments(db: Session, user: User) -> list[Investment]:
    return list(
        db.scalars(
            select(Investment)
            .where(Investment.user_id == user.id)
            .order_by(Investment.kind, Investment.name)
        )
    )


def create_investment(db: Session, user: User, data: dict[str, Any]) -> Investment:
    investment = Investment(user_id=user.id, **data)
    db.add(investment)
    db.commit()
    return investment


def update_investment(
    db: Session, user: User, investment_id: uuid.UUID, changes: dict[str, Any]
) -> Investment:
    investment = _owned(db, Investment, investment_id, user)
    for field, value in changes.items():
        setattr(investment, field, value)
    db.commit()
    return investment


def delete_investment(db: Session, user: User, investment_id: uuid.UUID) -> None:
    db.delete(_owned(db, Investment, investment_id, user))
    db.commit()


def emergency_reserve_total(db: Session, user: User) -> Decimal:
    return sum(
        (i.current_value for i in list_investments(db, user) if i.is_emergency_reserve), ZERO
    )
