"""v1.8: empréstimos a amigos com juros e parcelas (tela Divisões)."""

import unicodedata
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response, status
from pydantic import BaseModel, Field, model_validator

from app.api.deps import CurrentUser, DbSession
from app.services import personal_loans

router = APIRouter(tags=["empréstimos a amigos"])

Money = Annotated[Decimal, Field(gt=0, le=Decimal("10000000"), max_digits=12, decimal_places=2)]
Percent = Annotated[Decimal, Field(ge=0, le=100, max_digits=8, decimal_places=4)]
Mode = Literal["none", "total", "simple", "price", "sac"]
Frequency = Literal["day", "week", "biweek", "month"]
MAX_COUNT = {"day": 365, "week": 260, "biweek": 120, "month": 120}


class SimulateIn(BaseModel):
    principal: Money
    mode: Mode = "total"
    # O que a pessoa define: a taxa, ou o lucro, a parcela ou o total (e a taxa sai disso).
    target: Literal["rate", "profit", "installment", "total"] = "rate"
    rate: Annotated[Decimal, Field(ge=0, le=1000, max_digits=9, decimal_places=4)] | None = None
    value: Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)] | None = None
    frequency: Frequency = "month"
    count: Annotated[int, Field(ge=1, le=365)] = 1
    first_due: date
    market: bool = False

    @model_validator(mode="after")
    def _check(self) -> "SimulateIn":
        if self.count > MAX_COUNT[self.frequency]:
            raise ValueError("Quantidade de pagamentos grande demais para essa frequência.")
        if self.mode != "none" and self.target != "rate" and self.value is None:
            raise ValueError("Informe o valor que você quer definir.")
        return self


class LoanIn(SimulateIn):
    person: str = Field(min_length=1, max_length=60)
    description: str = Field(default="", max_length=120)
    direction: Literal["owes_me", "i_owe"] = "owes_me"
    late_fee: Percent | None = None
    late_interest: Percent | None = None


class RowOut(BaseModel):
    number: int
    due_date: date
    amount: Decimal
    interest: Decimal
    principal: Decimal
    balance: Decimal


class CompareOut(BaseModel):
    mode: str
    label: str
    rate: float
    first: Decimal
    last: Decimal


class MarketOut(BaseModel):
    cdi_year: float | None = None
    cdb_net: Decimal | None = None
    ipca_year: float | None = None
    real_profit: Decimal | None = None


class SimulateOut(BaseModel):
    mode: str
    rate: float
    frequency: str
    count: int
    principal: Decimal
    total: Decimal
    profit: Decimal
    installment: Decimal
    last_installment: Decimal
    equal_installments: bool
    monthly_equivalent: float
    yearly_equivalent: float
    usury_warning: bool
    payback: int | None
    stop_at: int
    loss_if_stops: Decimal
    schedule: list[RowOut]
    compare: list[CompareOut]
    market: MarketOut | None


class InstallmentOut(BaseModel):
    number: int
    due_date: date
    amount: Decimal
    interest: Decimal
    principal: Decimal
    received_amount: Decimal | None
    received_at: date | None
    open: Decimal
    status: Literal["paid", "partial", "late", "open"]
    late_charge: Decimal


class LoanOut(BaseModel):
    id: uuid.UUID
    person: str
    description: str | None
    direction: str
    principal: Decimal
    mode: str
    rate: Decimal
    frequency: str
    count: int
    first_due: date
    late_fee: Decimal | None
    late_interest: Decimal | None
    created_at: datetime
    settled_at: datetime | None
    total: Decimal
    received: Decimal
    remaining: Decimal
    profit: Decimal
    profit_received: Decimal
    paid_count: int
    late_count: int
    late_amount: Decimal
    next: InstallmentOut | None
    monthly_equivalent: float
    yearly_equivalent: float
    payback: int | None
    installments: list[InstallmentOut]


class LoanTotalsOut(BaseModel):
    lent: Decimal
    lent_count: int
    to_receive: Decimal
    profit_expected: Decimal
    profit_received: Decimal
    yearly: float | None
    late_count: int


class LoansOut(BaseModel):
    loans: list[LoanOut]
    totals: LoanTotalsOut


class ReceiveIn(BaseModel):
    number: Annotated[int, Field(ge=1)]
    amount: Money | None = None
    on: date | None = None


class PayoffIn(BaseModel):
    on: date | None = None
    discount: bool = True


class PayoffQuoteOut(BaseModel):
    remaining: Decimal
    discount: Decimal
    value: Decimal


def _out(db, loan) -> LoanOut:  # type: ignore[no-untyped-def]
    return LoanOut(**personal_loans.detail(db, loan))


@router.post("/friend-loans/simulate")
def simulate(body: SimulateIn, user: CurrentUser) -> SimulateOut:
    return SimulateOut(**personal_loans.simulate(body.model_dump()))


@router.get("/friend-loans")
def list_loans(user: CurrentUser, db: DbSession) -> LoansOut:
    loans = personal_loans.all_loans(db, user)
    return LoansOut(
        loans=[LoanOut(**x) for x in loans], totals=LoanTotalsOut(**personal_loans.totals(loans))
    )


@router.post("/friend-loans", status_code=status.HTTP_201_CREATED)
def create(body: LoanIn, user: CurrentUser, db: DbSession) -> LoanOut:
    return _out(db, personal_loans.create(db, user, body.model_dump()))


@router.get("/friend-loans/{loan_id}")
def get(loan_id: uuid.UUID, user: CurrentUser, db: DbSession) -> LoanOut:
    return _out(db, personal_loans._own(db, user, loan_id))


@router.delete("/friend-loans/{loan_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove(loan_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    personal_loans.remove(db, user, loan_id)


@router.post("/friend-loans/{loan_id}/receive")
def receive(loan_id: uuid.UUID, body: ReceiveIn, user: CurrentUser, db: DbSession) -> LoanOut:
    loan = personal_loans.receive(db, user, loan_id, body.number, body.amount, body.on)
    return _out(db, loan)


@router.delete("/friend-loans/{loan_id}/receive/{number}")
def undo(loan_id: uuid.UUID, number: int, user: CurrentUser, db: DbSession) -> LoanOut:
    return _out(db, personal_loans.undo(db, user, loan_id, number))


@router.get("/friend-loans/{loan_id}/payoff")
def payoff_quote(
    loan_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    on: date | None = None,
    discount: Annotated[bool, Query()] = True,
) -> PayoffQuoteOut:
    from app.core.months import today_local

    loan = personal_loans._own(db, user, loan_id)
    return PayoffQuoteOut(**personal_loans.payoff_quote(db, loan, on or today_local(), discount))


@router.post("/friend-loans/{loan_id}/payoff")
def payoff(loan_id: uuid.UUID, body: PayoffIn, user: CurrentUser, db: DbSession) -> LoanOut:
    return _out(db, personal_loans.payoff(db, user, loan_id, body.on, body.discount))


@router.get("/friend-loans/{loan_id}/term.pdf")
def term_pdf(loan_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    from app.services import pdf_export

    loan = personal_loans._own(db, user, loan_id)
    data = personal_loans.detail(db, loan)
    content = pdf_export.loan_term_pdf(data, user.display_name or user.email)
    plain = unicodedata.normalize("NFKD", loan.person).encode("ascii", "ignore").decode()
    slug = "".join(c for c in plain.lower() if c.isalnum()) or "pessoa"
    return Response(
        content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="termo-emprestimo_{slug}.pdf"'},
    )
