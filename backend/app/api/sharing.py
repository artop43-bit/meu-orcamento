"""v1.0: alertas do mês e divisão de despesas."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, DbSession
from app.core.months import parse_month
from app.services import alerts, budget, splits

router = APIRouter(tags=["alertas e divisões"])

Money = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]


# ---------------------------------------------------------------- alertas


class AlertOut(BaseModel):
    kind: Literal["unusual", "new_merchant", "price_up", "renewal"]
    key: str
    title: str
    text: str
    expense_id: uuid.UUID | None = None


@router.get("/alerts")
def month_alerts(user: CurrentUser, db: DbSession, month: str | None = None) -> list[AlertOut]:
    target = parse_month(month) if month else budget.current_month(user.month_start_day)
    return [AlertOut(**a) for a in alerts.month_alerts(db, user, target)]


# ---------------------------------------------------------------- divisões


class SplitPerson(BaseModel):
    person: str = Field(min_length=1, max_length=60)
    # Valor em reais (modo "amount") ou porcentagem (modo "percent"); ignorado em "equal".
    value: Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)] | None = None


class SplitIn(BaseModel):
    people: list[SplitPerson] = Field(min_length=1, max_length=20)
    mode: Literal["equal", "amount", "percent"] = "equal"
    include_me: bool = True


class ManualIn(BaseModel):
    person: str = Field(min_length=1, max_length=60)
    description: str = Field(default="", max_length=120)
    amount: Money
    direction: Literal["owes_me", "i_owe"]


class ShareOut(BaseModel):
    id: uuid.UUID
    expense_id: uuid.UUID | None
    person: str
    description: str
    amount: Decimal
    direction: str
    created_at: datetime
    settled_at: datetime | None


class PersonOut(BaseModel):
    person: str
    balance: Decimal
    items: list[ShareOut]


class BoardOut(BaseModel):
    people: list[PersonOut]
    owed_to_me: Decimal
    i_owe: Decimal
    names: list[str]
    history: list[ShareOut]


class SettleIn(BaseModel):
    person: str = Field(min_length=1, max_length=60)
    record_income: bool = True


class SettleOut(BaseModel):
    person: str
    balance: Decimal
    income_id: uuid.UUID | None


def _share(s) -> ShareOut:  # type: ignore[no-untyped-def]
    return ShareOut.model_validate(s, from_attributes=True)


@router.get("/splits")
def board(user: CurrentUser, db: DbSession) -> BoardOut:
    data = splits.board(db, user)
    return BoardOut(
        people=[
            PersonOut(
                person=p["person"], balance=p["balance"], items=[_share(s) for s in p["items"]]
            )
            for p in data["people"]
        ],
        owed_to_me=data["owed_to_me"],
        i_owe=data["i_owe"],
        names=data["names"],
        history=[_share(s) for s in data["history"]],
    )


@router.get("/expenses/{expense_id}/split")
def expense_split(expense_id: uuid.UUID, user: CurrentUser, db: DbSession) -> list[ShareOut]:
    from sqlalchemy import select

    from app.models import SplitShare

    rows = db.scalars(
        select(SplitShare).where(SplitShare.user_id == user.id, SplitShare.expense_id == expense_id)
    )
    return [_share(s) for s in rows]


@router.put("/expenses/{expense_id}/split")
def split_expense(
    expense_id: uuid.UUID, body: SplitIn, user: CurrentUser, db: DbSession
) -> list[ShareOut]:
    people = [p.model_dump() for p in body.people]
    created = splits.split_expense(db, user, expense_id, people, body.mode, body.include_me)
    return [_share(s) for s in created]


@router.post("/splits", status_code=status.HTTP_201_CREATED)
def add_manual(body: ManualIn, user: CurrentUser, db: DbSession) -> ShareOut:
    return _share(
        splits.add_manual(db, user, body.person, body.description, body.amount, body.direction)
    )


@router.delete("/splits/{share_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_share(share_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    splits.remove(db, user, share_id)


@router.post("/splits/settle")
def settle(body: SettleIn, user: CurrentUser, db: DbSession) -> SettleOut:
    month = budget.current_month(user.month_start_day)
    return SettleOut(**splits.settle(db, user, body.person, month, body.record_income))
