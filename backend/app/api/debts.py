"""v1.0: financiamentos e empréstimos, outras dívidas e patrimônio."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, status
from pydantic import BaseModel, Field, model_validator

from app.api.deps import CurrentUser, DbSession
from app.services import loans

router = APIRouter(tags=["dívidas e patrimônio"])

Money = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
OptionalMoney = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
LoanKind = Literal["home", "vehicle", "personal", "payroll", "overdraft", "other"]


class LoanIn(BaseModel):
    kind: LoanKind = "personal"
    name: str = Field(min_length=1, max_length=80)
    institution: str | None = Field(default=None, max_length=80)
    principal: Money
    rate: Annotated[Decimal, Field(ge=0, le=100, max_digits=8, decimal_places=4)]
    rate_period: Literal["monthly", "yearly"] = "monthly"
    system: Literal["price", "sac"] = "price"
    installments: Annotated[int, Field(ge=1, le=420)]
    first_due: date
    paid_before: Annotated[int, Field(ge=0, le=419)] = 0
    insurance_monthly: OptionalMoney = Decimal("0")
    fee_monthly: OptionalMoney = Decimal("0")
    iof: OptionalMoney = Decimal("0")
    category_id: uuid.UUID | None = None
    account_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _dates(self) -> "LoanIn":
        if not date(2000, 1, 1) <= self.first_due <= date(2100, 12, 31):
            raise ValueError("Data da primeira parcela fora do intervalo aceito.")
        return self


class LoanPatch(BaseModel):
    kind: LoanKind | None = None
    name: str | None = Field(default=None, min_length=1, max_length=80)
    institution: str | None = Field(default=None, max_length=80)
    principal: Money | None = None
    rate: Annotated[Decimal, Field(ge=0, le=100, max_digits=8, decimal_places=4)] | None = None
    rate_period: Literal["monthly", "yearly"] | None = None
    system: Literal["price", "sac"] | None = None
    installments: Annotated[int, Field(ge=1, le=420)] | None = None
    first_due: date | None = None
    paid_before: Annotated[int, Field(ge=0, le=419)] | None = None
    insurance_monthly: OptionalMoney | None = None
    fee_monthly: OptionalMoney | None = None
    iof: OptionalMoney | None = None
    category_id: uuid.UUID | None = None
    account_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=500)


class LoanOut(BaseModel):
    id: uuid.UUID
    kind: str
    kind_label: str
    name: str
    institution: str | None
    principal: Decimal
    rate: Decimal
    rate_period: str
    system: str
    installments: int
    first_due: date
    paid_before: int
    insurance_monthly: Decimal
    fee_monthly: Decimal
    iof: Decimal
    category_id: uuid.UUID | None
    account_id: uuid.UUID | None
    notes: str | None
    monthly_rate: float
    yearly_rate: float
    cet_monthly: float
    cet_yearly: float
    first_payment: Decimal
    last_payment: Decimal
    total_paid: Decimal
    total_interest: Decimal
    paid_installments: int
    balance: Decimal
    next_payment: Decimal | None
    next_due: date | None
    end: date


def _loan(data: dict[str, Any]) -> LoanOut:
    loan = data["loan"]
    fields = {c.name: getattr(loan, c.name) for c in loan.__table__.columns}
    return LoanOut(**fields, **{k: v for k, v in data.items() if k != "loan"})


class Installment(BaseModel):
    number: int
    due: date
    payment: Decimal
    interest: Decimal
    amortization: Decimal
    extras: Decimal
    balance: Decimal


class ExtraIn(BaseModel):
    amount: Money
    after: Annotated[int, Field(ge=0, le=419)] | None = None
    mode: Literal["term", "payment"] = "term"


class ExtraOut(BaseModel):
    after: int
    balance_before: Decimal
    amount: Decimal
    mode: str
    months_before: int
    months_after: int
    payment_before: Decimal
    payment_after: Decimal
    interest_before: Decimal
    interest_after: Decimal
    interest_saved: Decimal
    end_after: date | None


class OtherDebtIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    balance: OptionalMoney
    monthly_payment: OptionalMoney | None = None
    notes: str | None = Field(default=None, max_length=500)


class OtherDebtOut(OtherDebtIn):
    id: uuid.UUID


class HistoryPoint(BaseModel):
    month: date
    assets: Decimal
    debts: Decimal
    net: Decimal


class DebtsOverview(BaseModel):
    loans: list[LoanOut]
    others: list[OtherDebtOut]
    card_installments: Decimal
    debts: Decimal
    monthly_payments: Decimal
    assets: Decimal
    investments: Decimal
    accounts: Decimal
    net_worth: Decimal
    history: list[HistoryPoint]


@router.get("/debts")
def debts_overview(user: CurrentUser, db: DbSession) -> DebtsOverview:
    data = loans.overview(db, user)
    return DebtsOverview(
        **{k: v for k, v in data.items() if k not in ("loans", "others", "history")},
        loans=[_loan(item) for item in data["loans"]],
        others=[OtherDebtOut.model_validate(d, from_attributes=True) for d in data["others"]],
        history=[HistoryPoint(**h) for h in data["history"]],
    )


@router.post("/loans", status_code=status.HTTP_201_CREATED)
def create_loan(body: LoanIn, user: CurrentUser, db: DbSession) -> LoanOut:
    loan = loans.create(db, user, body.model_dump())
    return _loan(loans.summary(db, loan))


@router.patch("/loans/{loan_id}")
def update_loan(loan_id: uuid.UUID, body: LoanPatch, user: CurrentUser, db: DbSession) -> LoanOut:
    loan = loans.update(db, user, loan_id, body.model_dump(exclude_unset=True))
    return _loan(loans.summary(db, loan))


@router.delete("/loans/{loan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_loan(loan_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    loans.remove(db, user, loan_id)


@router.get("/loans/{loan_id}/table")
def loan_table(loan_id: uuid.UUID, user: CurrentUser, db: DbSession) -> list[Installment]:
    loan = loans._owned(db, user, loan_id)
    return [Installment(**row) for row in loans.table(loan)]


@router.post("/loans/{loan_id}/simulate")
def simulate(loan_id: uuid.UUID, body: ExtraIn, user: CurrentUser, db: DbSession) -> ExtraOut:
    loan = loans._owned(db, user, loan_id)
    return ExtraOut(**loans.simulate_extra(db, loan, body.amount, body.after, body.mode))


@router.post("/other-debts", status_code=status.HTTP_201_CREATED)
def create_other(body: OtherDebtIn, user: CurrentUser, db: DbSession) -> OtherDebtOut:
    debt = loans.save_other(db, user, body.model_dump())
    return OtherDebtOut.model_validate(debt, from_attributes=True)


@router.put("/other-debts/{debt_id}")
def update_other(
    debt_id: uuid.UUID, body: OtherDebtIn, user: CurrentUser, db: DbSession
) -> OtherDebtOut:
    debt = loans.save_other(db, user, body.model_dump(), debt_id)
    return OtherDebtOut.model_validate(debt, from_attributes=True)


@router.delete("/other-debts/{debt_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_other(debt_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    loans.remove_other(db, user, debt_id)
