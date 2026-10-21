"""v1.3: desafios de economia e o plano "sem culpa" para o mês no negativo."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, status
from pydantic import BaseModel, Field, StringConstraints

from app.api.deps import CurrentUser, DbSession
from app.core.months import parse_month
from app.services import challenges, recovery

router = APIRouter(tags=["hábitos"])

ChallengeKind = Literal["no_keyword", "no_category", "no_nonessential", "max_category"]


class TemplateOut(BaseModel):
    key: str
    title: str
    kind: ChallengeKind
    days: int
    text: str
    category: str | None = None


class ChallengeIn(BaseModel):
    template: str | None = None
    title: Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)] | None = None
    kind: ChallengeKind | None = None
    category_id: uuid.UUID | None = None
    keywords: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None
    max_amount: Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)] | None = None
    days: Annotated[int, Field(ge=3, le=90)] | None = None


class Slip(BaseModel):
    description: str
    amount: Decimal
    date: date


class ChallengeOut(BaseModel):
    id: uuid.UUID
    title: str
    kind: ChallengeKind
    category_id: uuid.UUID | None
    keywords: str | None
    max_amount: Decimal | None
    start_date: date
    end_date: date
    days: int
    elapsed_days: int
    status: Literal["active", "won", "lost"]
    spent: Decimal
    slips: list[Slip]


def _out(row: dict) -> ChallengeOut:  # type: ignore[type-arg]
    c = row["challenge"]
    return ChallengeOut(
        id=c.id,
        title=c.title,
        kind=c.kind,
        category_id=c.category_id,
        keywords=c.keywords,
        max_amount=c.max_amount,
        start_date=c.start_date,
        end_date=row["end_date"],
        days=c.days,
        elapsed_days=row["elapsed_days"],
        status=row["status"],
        spent=row["spent"],
        slips=[Slip(**s) for s in row["slips"]],
    )


@router.get("/challenges/templates")
def templates(_: CurrentUser) -> list[TemplateOut]:
    return [
        TemplateOut(**{k: v for k, v in t.items() if k != "keywords"}) for t in challenges.TEMPLATES
    ]


@router.get("/challenges")
def list_challenges(user: CurrentUser, db: DbSession) -> list[ChallengeOut]:
    return [_out(row) for row in challenges.overview(db, user)]


@router.post("/challenges", status_code=status.HTTP_201_CREATED)
def create_challenge(body: ChallengeIn, user: CurrentUser, db: DbSession) -> ChallengeOut:
    challenge = challenges.create(db, user, body.model_dump())
    return _out({"challenge": challenge, **challenges.progress(db, user, challenge)})


@router.delete("/challenges/{challenge_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_challenge(challenge_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    challenges.remove(db, user, challenge_id)


class Spread(BaseModel):
    months: int
    per_month: Decimal


class Cut(BaseModel):
    category_id: uuid.UUID | None
    name: str
    total: Decimal
    average: Decimal
    above_average: Decimal


class FixedCost(BaseModel):
    description: str
    monthly: Decimal


class RecoveryOut(BaseModel):
    month: date
    deficit: Decimal
    spread: list[Spread]
    cuts: list[Cut]
    fixed: list[FixedCost]


@router.get("/months/{month}/recovery")
def recovery_plan(month: str, user: CurrentUser, db: DbSession) -> RecoveryOut:
    """Plano passo a passo para equilibrar um mês com despesas acima das receitas."""
    return RecoveryOut(**recovery.plan(db, user, parse_month(month)))
