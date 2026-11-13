"""v1.0: dividir despesas e placar de quem deve a quem.

Ao dividir uma despesa que o usuário pagou, cada pessoa fica devendo a parte dela
("owes_me"). Também dá para anotar o contrário: o usuário deve a alguém ("i_owe"). O placar
soma, por pessoa, o que está em aberto; "Acertar contas" quita tudo com a pessoa e, se ela
pagou o usuário, pode lançar o reembolso como receita do mês.
"""

import uuid
from collections import defaultdict
from datetime import date
from decimal import ROUND_DOWN, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.types import utcnow
from app.models import Expense, Income, SplitShare, User

CENT = Decimal("0.01")
ZERO = Decimal("0")


def _name(person: str) -> str:
    name = " ".join(person.split())
    if not name:
        raise AppError(400, "invalid_person", "Informe o nome da pessoa.")
    return name[:60]


def _key(person: str) -> str:
    return _name(person).casefold()


def shares_for(
    total: Decimal, people: list[dict[str, Any]], mode: str, include_me: bool
) -> list[tuple[str, Decimal]]:
    """Partes de cada pessoa. mode: "equal" (com ou sem o usuário), "amount" ou "percent"."""
    if not people:
        raise AppError(400, "no_people", "Adicione pelo menos uma pessoa.")
    names = [_name(p["person"]) for p in people]
    if len({n.casefold() for n in names}) != len(names):
        raise AppError(400, "duplicate_person", "Cada pessoa aparece uma vez na divisão.")
    if mode == "equal":
        count = len(names) + (1 if include_me else 0)
        part = (total / count).quantize(CENT, rounding=ROUND_DOWN)
        # Centavos que sobram ficam com quem pagou (o usuário), nunca a mais para os outros.
        return [(n, part) for n in names]
    values = [Decimal(str(p.get("value") or 0)) for p in people]
    if any(v <= 0 for v in values):
        raise AppError(400, "invalid_share", "Informe um valor maior que zero para cada pessoa.")
    if mode == "percent":
        if sum(values) > 100:
            raise AppError(400, "invalid_share", "As porcentagens somam mais de 100%.")
        return [(n, (total * v / 100).quantize(CENT)) for n, v in zip(names, values, strict=True)]
    if sum(values) > total:
        raise AppError(400, "invalid_share", "As partes somam mais que o valor da despesa.")
    return [(n, v.quantize(CENT)) for n, v in zip(names, values, strict=True)]


def split_expense(
    db: Session,
    user: User,
    expense_id: uuid.UUID,
    people: list[dict[str, Any]],
    mode: str,
    include_me: bool,
) -> list[SplitShare]:
    expense = db.get(Expense, expense_id)
    if expense is None or expense.user_id != user.id:
        raise AppError(404, "not_found", "Despesa não encontrada.")
    # Dividir de novo substitui a divisão anterior (as partes já acertadas ficam).
    for old in db.scalars(
        select(SplitShare).where(
            SplitShare.expense_id == expense.id, SplitShare.settled_at.is_(None)
        )
    ):
        db.delete(old)
    created = []
    for person, amount in shares_for(expense.amount, people, mode, include_me):
        share = SplitShare(
            user_id=user.id,
            expense_id=expense.id,
            person=person,
            description=expense.description,
            amount=amount,
            direction="owes_me",
        )
        db.add(share)
        created.append(share)
    db.commit()
    return created


def add_manual(
    db: Session, user: User, person: str, description: str, amount: Decimal, direction: str
) -> SplitShare:
    share = SplitShare(
        user_id=user.id,
        person=_name(person),
        description=description.strip()[:120] or "Sem descrição",
        amount=amount,
        direction=direction,
    )
    db.add(share)
    db.commit()
    return share


def remove(db: Session, user: User, share_id: uuid.UUID) -> None:
    share = db.get(SplitShare, share_id)
    if share is None or share.user_id != user.id:
        raise AppError(404, "not_found", "Item não encontrado.")
    db.delete(share)
    db.commit()


def board(db: Session, user: User) -> dict[str, Any]:
    """Placar por pessoa: positivo = a pessoa deve ao usuário; negativo = o usuário deve."""
    open_shares = list(
        db.scalars(
            select(SplitShare)
            .where(SplitShare.user_id == user.id, SplitShare.settled_at.is_(None))
            .order_by(SplitShare.created_at.desc())
        )
    )
    from app.services import personal_loans

    loans = personal_loans.all_loans(db, user)
    people: dict[str, dict[str, Any]] = {}
    totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for share in open_shares:
        key = share.person.casefold()
        entry = people.setdefault(key, {"person": share.person, "items": [], "loans": []})
        entry["items"].append(share)
        totals[key] += share.amount if share.direction == "owes_me" else -share.amount
    # v1.8: empréstimos com juros entram na linha da pessoa (o que falta pagar conta no saldo).
    for loan in loans:
        key = loan["person"].casefold()
        if loan["settled_at"] and key not in people:
            continue
        entry = people.setdefault(key, {"person": loan["person"], "items": [], "loans": []})
        entry["loans"].append(loan)
        sign = 1 if loan["direction"] == "owes_me" else -1
        totals[key] += sign * loan["remaining"]
    rows = [
        {**entry, "balance": totals[key]}
        for key, entry in people.items()
        if entry["items"] or entry["loans"]
    ]
    rows.sort(key=lambda r: abs(r["balance"]), reverse=True)
    history = list(
        db.scalars(
            select(SplitShare)
            .where(SplitShare.user_id == user.id, SplitShare.settled_at.is_not(None))
            .order_by(SplitShare.settled_at.desc())
            .limit(30)
        )
    )
    return {
        "people": rows,
        "owed_to_me": sum((r["balance"] for r in rows if r["balance"] > 0), ZERO),
        "i_owe": -sum((r["balance"] for r in rows if r["balance"] < 0), ZERO),
        "names": sorted(
            {s.person for s in open_shares + history} | {x["person"] for x in loans},
            key=str.casefold,
        ),
        "history": history,
        "loans": personal_loans.totals(loans),
    }


def settle(
    db: Session, user: User, person: str, month: date, record_income: bool
) -> dict[str, Any]:
    """Acerta as contas com a pessoa: quita as partes em aberto e, se ela pagou o saldo ao
    usuário, lança o reembolso como receita do mês (opcional)."""
    key = _key(person)
    shares = [
        s
        for s in db.scalars(
            select(SplitShare).where(SplitShare.user_id == user.id, SplitShare.settled_at.is_(None))
        )
        if s.person.casefold() == key
    ]
    if not shares:
        raise AppError(404, "not_found", "Nada em aberto com essa pessoa.")
    balance = sum((s.amount if s.direction == "owes_me" else -s.amount for s in shares), ZERO)
    now = utcnow()
    for s in shares:
        s.settled_at = now
    income = None
    if record_income and balance > 0:
        income = Income(
            user_id=user.id,
            month=month,
            description=f"Reembolso de {shares[0].person}"[:120],
            amount=balance,
            income_type="variable",
        )
        db.add(income)
    db.commit()
    return {
        "person": shares[0].person,
        "balance": balance,
        "income_id": income.id if income else None,
    }
