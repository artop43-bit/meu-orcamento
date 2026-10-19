"""v0.7: contas e saldos, transferências, para revisar, busca, ritmo e cópia do mês anterior."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Query, status

from app.api.budget import _changes
from app.api.deps import CurrentUser, DbSession
from app.core.months import current_month, parse_month
from app.schemas.budget import (
    AccountBalance,
    AccountIn,
    AccountOut,
    AccountPatch,
    CopyIn,
    ExpenseOut,
    PaceRow,
    ReviewConfirmIn,
    SafeDate,
    SearchOut,
    TransferIn,
    TransferOut,
)
from app.services import money

router = APIRouter(tags=["contas, revisar e busca"])


@router.get("/accounts")
def list_accounts(user: CurrentUser, db: DbSession) -> list[AccountBalance]:
    """Contas com o saldo de hoje e o previsto para o fim do mês."""
    return [
        AccountBalance.model_validate({**b, "account": AccountOut.model_validate(b["account"])})
        for b in money.balances(db, user)
    ]


@router.post("/accounts", status_code=status.HTTP_201_CREATED)
def create_account(body: AccountIn, user: CurrentUser, db: DbSession) -> AccountOut:
    return AccountOut.model_validate(money.create_account(db, user, body.model_dump()))


@router.patch("/accounts/{account_id}")
def update_account(
    account_id: uuid.UUID, body: AccountPatch, user: CurrentUser, db: DbSession
) -> AccountOut:
    changes = _changes(body, nullable={"color"})
    return AccountOut.model_validate(money.update_account(db, user, account_id, changes))


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(account_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    money.delete_account(db, user, account_id)


@router.get("/transfers")
def list_transfers(user: CurrentUser, db: DbSession, month: str | None = None) -> list[TransferOut]:
    target = parse_month(month) if month else None
    return [TransferOut.model_validate(t) for t in money.list_transfers(db, user, target)]


@router.post("/transfers", status_code=status.HTTP_201_CREATED)
def create_transfer(body: TransferIn, user: CurrentUser, db: DbSession) -> TransferOut:
    return TransferOut.model_validate(money.create_transfer(db, user, body.model_dump()))


@router.delete("/transfers/{transfer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transfer(transfer_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    money.delete_transfer(db, user, transfer_id)


@router.get("/review")
def review(user: CurrentUser, db: DbSession) -> list[ExpenseOut]:
    """Despesas vindas do extrato que ainda não foram conferidas."""
    return [ExpenseOut.model_validate(e) for e in money.review_queue(db, user)]


@router.post("/review/confirm")
def confirm_review(body: ReviewConfirmIn, user: CurrentUser, db: DbSession) -> dict[str, int]:
    count = money.confirm_review(db, user, body.ids, body.category_id, body.categories)
    return {"count": count}


@router.get("/search")
def search(
    user: CurrentUser,
    db: DbSession,
    q: Annotated[str, Query(max_length=120)] = "",
    start: SafeDate | None = None,
    end: SafeDate | None = None,
    min_amount: Annotated[Decimal | None, Query(ge=0)] = None,
    max_amount: Annotated[Decimal | None, Query(ge=0)] = None,
    payment_method: str | None = None,
    category_id: uuid.UUID | None = None,
    kind: Literal["all", "expense", "income"] = "all",
) -> SearchOut:
    data = money.search(
        db, user, q, start, end, min_amount, max_amount, payment_method, category_id, kind
    )
    return SearchOut.model_validate(data)


@router.get("/analysis/pace")
def pace(user: CurrentUser, db: DbSession, month: str | None = None) -> list[PaceRow]:
    target = parse_month(month) if month else current_month()
    return [PaceRow.model_validate(r) for r in money.pace(db, user, target, date.today())]


@router.get("/months/{month}/copy-candidates")
def copy_candidates(month: str, user: CurrentUser, db: DbSession) -> list[ExpenseOut]:
    items = money.copy_candidates(db, user, parse_month(month))
    return [ExpenseOut.model_validate(e) for e in items]


@router.post("/months/{month}/copy-previous", status_code=status.HTTP_201_CREATED)
def copy_previous(month: str, body: CopyIn, user: CurrentUser, db: DbSession) -> list[ExpenseOut]:
    created = money.copy_previous(db, user, parse_month(month), body.ids)
    return [ExpenseOut.model_validate(e) for e in created]
