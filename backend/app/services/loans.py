"""v1.0: financiamentos e empréstimos, outras dívidas e patrimônio mês a mês.

Matemática (juros compostos, valores em reais com centavos):
- Taxa anual → mensal: (1 + a)^(1/12) − 1.
- Price: parcela fixa P·i / (1 − (1 + i)^−n); a última absorve a diferença de centavos.
- SAC: amortização fixa P / n; juros sobre o saldo, então a parcela cai.
- Seguro e taxa mensal entram em cada parcela; o IOF é somado ao valor financiado.
- CET: taxa mensal que iguala o valor recebido às parcelas pagas (bissecção), anualizada.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.months import add_months, with_day
from app.db.types import utcnow
from app.models import (
    Category,
    Expense,
    Investment,
    Loan,
    NetWorthSnapshot,
    OtherDebt,
    User,
)

CENT = Decimal("0.01")
ZERO = Decimal("0")
KIND_LABELS = {
    "home": "Financiamento imobiliário",
    "vehicle": "Financiamento de veículo",
    "personal": "Empréstimo pessoal",
    "payroll": "Empréstimo consignado",
    "overdraft": "Cheque especial",
    "other": "Outro financiamento",
}
# Categoria padrão das parcelas, por tipo (se a pessoa não escolher).
KIND_CATEGORY = {"home": "Moradia", "vehicle": "Transporte"}


def money(value: Decimal | float) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def monthly_rate(rate: Decimal, period: str) -> float:
    """Taxa mensal em fração (1,5% → 0,015)."""
    value = float(rate) / 100
    return (1 + value) ** (1 / 12) - 1 if period == "yearly" else value


def yearly_from_monthly(monthly: float) -> float:
    return (1 + monthly) ** 12 - 1


@dataclass
class Row:
    number: int
    payment: Decimal  # parcela total (amortização + juros + seguro + taxa)
    interest: Decimal
    amortization: Decimal
    extras: Decimal
    balance: Decimal  # saldo devedor depois desta parcela


def schedule(
    principal: Decimal,
    i: float,
    n: int,
    system: str,
    extras: Decimal = ZERO,
    start_balance: Decimal | None = None,
    fixed_payment: Decimal | None = None,
) -> list[Row]:
    """Tabela de amortização. `fixed_payment` (Price) permite recalcular o prazo depois de uma
    amortização extra mantendo a parcela."""
    balance = start_balance if start_balance is not None else principal
    rows: list[Row] = []
    if n <= 0 or balance <= 0:
        return rows
    if system == "price":
        if fixed_payment is not None:
            pmt = fixed_payment
        elif i == 0:
            pmt = money(balance / n)
        else:
            pmt = money(float(balance) * i / (1 - (1 + i) ** -n))
        number = 0
        while balance > 0 and number < 1200:
            number += 1
            interest = money(float(balance) * i)
            amort = pmt - interest
            if amort <= 0:
                raise AppError(400, "payment_too_low", "A parcela não cobre os juros do mês.")
            last = number == n if fixed_payment is None else amort >= balance
            if last or amort > balance:
                amort = balance
            balance -= amort
            rows.append(Row(number, amort + interest + extras, interest, amort, extras, balance))
            if fixed_payment is None and number >= n:
                break
        return rows
    amort_fixed = money(balance / n)
    for number in range(1, n + 1):
        interest = money(float(balance) * i)
        amort = balance if number == n else min(amort_fixed, balance)
        balance -= amort
        rows.append(Row(number, amort + interest + extras, interest, amort, extras, balance))
        if balance <= 0:
            break
    return rows


def cet_monthly(received: Decimal, payments: list[Decimal]) -> float:
    """Taxa mensal que zera o fluxo (valor recebido − parcelas descontadas)."""

    def npv(rate: float) -> float:
        return float(received) - sum(
            float(p) / (1 + rate) ** (k + 1) for k, p in enumerate(payments)
        )

    low, high = 0.0, 1.0
    if npv(low) >= 0:
        return 0.0
    for _ in range(200):
        mid = (low + high) / 2
        if npv(mid) < 0:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def _extras(loan: Loan) -> Decimal:
    return (loan.insurance_monthly or ZERO) + (loan.fee_monthly or ZERO)


def loan_rows(loan: Loan) -> list[Row]:
    i = monthly_rate(loan.rate, loan.rate_period)
    return schedule(
        loan.principal + (loan.iof or ZERO), i, loan.installments, loan.system, _extras(loan)
    )


def due_for(loan: Loan, number: int) -> date:
    """Vencimento da parcela: mesmo dia da primeira (ajustado nos meses mais curtos)."""
    return with_day(add_months(loan.first_due.replace(day=1), number - 1), loan.first_due.day)


# ---------------------------------------------------------------- parcelas no orçamento


def _category(db: Session, user: User, loan: Loan) -> uuid.UUID | None:
    if loan.category_id:
        return loan.category_id
    name = KIND_CATEGORY.get(loan.kind, "Outros")
    return db.scalar(select(Category.id).where(Category.user_id == user.id, Category.name == name))


def _materialize(db: Session, user: User, loan: Loan) -> None:
    """Cria as despesas das parcelas ainda não pagas (as já pagas ficam como estão)."""
    paid_numbers = set(
        db.scalars(
            select(Expense.installment_number).where(
                Expense.loan_id == loan.id, Expense.paid.is_(True)
            )
        )
    )
    db.execute(delete(Expense).where(Expense.loan_id == loan.id, Expense.paid.is_(False)))
    category = _category(db, user, loan)
    for row in loan_rows(loan):
        if row.number <= loan.paid_before or row.number in paid_numbers:
            continue
        due = due_for(loan, row.number)
        db.add(
            Expense(
                user_id=user.id,
                month=due.replace(day=1),
                description=f"{loan.name} ({row.number}/{loan.installments})"[:120],
                amount=row.payment,
                category_id=category,
                due_date=due,
                payment_method="boleto",
                account_id=loan.account_id,
                installment_group_id=loan.id,
                installment_number=row.number,
                installment_total=loan.installments,
                loan_id=loan.id,
            )
        )


def _owned(db: Session, user: User, loan_id: uuid.UUID) -> Loan:
    loan = db.get(Loan, loan_id)
    if loan is None or loan.user_id != user.id:
        raise AppError(404, "not_found", "Financiamento não encontrado.")
    return loan


def _validate(data: dict[str, Any]) -> None:
    if data["paid_before"] >= data["installments"]:
        raise AppError(
            400, "invalid_paid", "As parcelas já pagas precisam ser menos que o total de parcelas."
        )
    # Confere se a tabela fecha (ex.: parcela que não cobre os juros).
    loan = Loan(**{k: v for k, v in data.items() if k in Loan.__table__.columns})
    loan_rows(loan)


def create(db: Session, user: User, data: dict[str, Any]) -> Loan:
    _validate(data)
    loan = Loan(user_id=user.id, **data)
    db.add(loan)
    db.flush()
    _materialize(db, user, loan)
    db.commit()
    return loan


def update(db: Session, user: User, loan_id: uuid.UUID, changes: dict[str, Any]) -> Loan:
    loan = _owned(db, user, loan_id)
    merged = {c.name: getattr(loan, c.name) for c in Loan.__table__.columns} | changes
    _validate(merged)
    for key, value in changes.items():
        setattr(loan, key, value)
    _materialize(db, user, loan)
    db.commit()
    return loan


def remove(db: Session, user: User, loan_id: uuid.UUID) -> None:
    """Exclui o contrato e as parcelas a pagar; as já pagas ficam no histórico."""
    loan = _owned(db, user, loan_id)
    db.execute(delete(Expense).where(Expense.loan_id == loan.id, Expense.paid.is_(False)))
    db.delete(loan)
    db.commit()


def list_loans(db: Session, user: User) -> list[Loan]:
    return list(db.scalars(select(Loan).where(Loan.user_id == user.id).order_by(Loan.created_at)))


def paid_count(db: Session, loan: Loan) -> int:
    paid = (
        db.scalar(select(func.count()).where(Expense.loan_id == loan.id, Expense.paid.is_(True)))
        or 0
    )
    return min(loan.installments, loan.paid_before + paid)


def summary(db: Session, loan: Loan) -> dict[str, Any]:
    rows = loan_rows(loan)
    paid = paid_count(db, loan)
    i = monthly_rate(loan.rate, loan.rate_period)
    received = loan.principal
    cet = cet_monthly(received, [r.payment for r in rows])
    balance = rows[paid - 1].balance if paid > 0 else loan.principal + (loan.iof or ZERO)
    upcoming = next((r for r in rows if r.number == paid + 1), None)
    return {
        "loan": loan,
        "kind_label": KIND_LABELS.get(loan.kind, "Financiamento"),
        "monthly_rate": round(i * 100, 4),
        "yearly_rate": round(yearly_from_monthly(i) * 100, 4),
        "cet_monthly": round(cet * 100, 4),
        "cet_yearly": round(yearly_from_monthly(cet) * 100, 4),
        "first_payment": rows[0].payment if rows else ZERO,
        "last_payment": rows[-1].payment if rows else ZERO,
        "total_paid": sum((r.payment for r in rows), ZERO),
        "total_interest": sum((r.interest for r in rows), ZERO),
        "paid_installments": paid,
        "balance": balance if paid < loan.installments else ZERO,
        "next_payment": upcoming.payment if upcoming else None,
        "next_due": due_for(loan, upcoming.number) if upcoming else None,
        "end": due_for(loan, loan.installments),
    }


def table(loan: Loan) -> list[dict[str, Any]]:
    return [
        {
            "number": r.number,
            "due": due_for(loan, r.number),
            "payment": r.payment,
            "interest": r.interest,
            "amortization": r.amortization,
            "extras": r.extras,
            "balance": r.balance,
        }
        for r in loan_rows(loan)
    ]


def simulate_extra(
    db: Session, loan: Loan, amount: Decimal, after: int | None, mode: str
) -> dict[str, Any]:
    """Amortização extra depois da parcela `after` (padrão: a última paga).

    mode "term": mantém a parcela e encurta o prazo; "payment": mantém o prazo e reduz a parcela.
    """
    rows = loan_rows(loan)
    after = paid_count(db, loan) if after is None else after
    if not 0 <= after < len(rows):
        raise AppError(400, "invalid_installment", "Escolha uma parcela que ainda não venceu.")
    balance = rows[after - 1].balance if after > 0 else loan.principal + (loan.iof or ZERO)
    if amount <= 0 or amount > balance:
        raise AppError(
            400, "invalid_amount", "O valor precisa ser maior que zero e até o saldo devedor."
        )
    i = monthly_rate(loan.rate, loan.rate_period)
    extras = _extras(loan)
    remaining = len(rows) - after
    new_balance = balance - amount
    if mode == "term":
        if loan.system == "price":
            pmt = rows[after].payment - extras
            new_rows = schedule(new_balance, i, remaining, "price", extras, fixed_payment=pmt)
        else:
            # SAC: mantém a amortização mensal; o prazo encurta.
            amort = rows[after].amortization
            months = max(1, int((new_balance / amort).to_integral_value(rounding="ROUND_CEILING")))
            new_rows = schedule(new_balance, i, months, "sac", extras)
    else:
        new_rows = schedule(new_balance, i, remaining, loan.system, extras)
    before = rows[after:]
    interest_before = sum((r.interest for r in before), ZERO)
    interest_after = sum((r.interest for r in new_rows), ZERO)
    return {
        "after": after,
        "balance_before": balance,
        "amount": amount,
        "mode": mode,
        "months_before": len(before),
        "months_after": len(new_rows),
        "payment_before": before[0].payment if before else ZERO,
        "payment_after": new_rows[0].payment if new_rows else ZERO,
        "interest_before": interest_before,
        "interest_after": interest_after,
        "interest_saved": interest_before - interest_after,
        "end_after": due_for(loan, after + len(new_rows)) if new_rows else None,
    }


# ---------------------------------------------------------------- outras dívidas


def list_other(db: Session, user: User) -> list[OtherDebt]:
    return list(
        db.scalars(select(OtherDebt).where(OtherDebt.user_id == user.id).order_by(OtherDebt.name))
    )


def save_other(
    db: Session, user: User, data: dict[str, Any], debt_id: uuid.UUID | None = None
) -> OtherDebt:
    if debt_id is None:
        debt = OtherDebt(user_id=user.id, **data)
        db.add(debt)
    else:
        debt = db.get(OtherDebt, debt_id)  # type: ignore[assignment]
        if debt is None or debt.user_id != user.id:
            raise AppError(404, "not_found", "Dívida não encontrada.")
        for key, value in data.items():
            setattr(debt, key, value)
        debt.updated_at = utcnow()
    db.commit()
    return debt


def remove_other(db: Session, user: User, debt_id: uuid.UUID) -> None:
    debt = db.get(OtherDebt, debt_id)
    if debt is None or debt.user_id != user.id:
        raise AppError(404, "not_found", "Dívida não encontrada.")
    db.delete(debt)
    db.commit()


# ---------------------------------------------------------------- visão geral e patrimônio


def card_installments(db: Session, user: User, month: date) -> Decimal:
    """Parcelas futuras de compras no cartão (já assumidas, ainda não chegaram na fatura)."""
    return (
        db.scalar(
            select(func.coalesce(func.sum(Expense.amount), 0)).where(
                Expense.user_id == user.id,
                Expense.card_id.is_not(None),
                Expense.installment_group_id.is_not(None),
                Expense.loan_id.is_(None),
                Expense.paid.is_(False),
                Expense.month > month,
            )
        )
        or ZERO
    )


def overview(db: Session, user: User, today: date | None = None) -> dict[str, Any]:
    from app.services import money as money_service
    from app.services.budget import current_month

    month = today.replace(day=1) if today else current_month()
    today = today or date.today()
    loans = [summary(db, loan) for loan in list_loans(db, user)]
    others = list_other(db, user)
    cards = Decimal(card_installments(db, user, month))
    loans_balance = sum((s["balance"] for s in loans), ZERO)
    others_balance = sum((d.balance for d in others), ZERO)
    debts = loans_balance + others_balance + cards
    monthly = sum((s["next_payment"] or ZERO for s in loans), ZERO) + sum(
        (d.monthly_payment or ZERO for d in others), ZERO
    )
    investments = (
        db.scalar(
            select(func.coalesce(func.sum(Investment.current_value), 0)).where(
                Investment.user_id == user.id
            )
        )
        or ZERO
    )
    accounts = sum((max(ZERO, b["balance"]) for b in money_service.balances(db, user, today)), ZERO)
    assets = Decimal(investments) + accounts
    _snapshot(db, user, month, assets, debts)
    history = list(
        db.scalars(
            select(NetWorthSnapshot)
            .where(NetWorthSnapshot.user_id == user.id)
            .order_by(NetWorthSnapshot.month)
        )
    )
    return {
        "loans": loans,
        "others": others,
        "card_installments": cards,
        "debts": debts,
        "monthly_payments": monthly,
        "assets": assets,
        "investments": Decimal(investments),
        "accounts": accounts,
        "net_worth": assets - debts,
        "history": [
            {"month": h.month, "assets": h.assets, "debts": h.debts, "net": h.assets - h.debts}
            for h in history
        ],
    }


def _snapshot(db: Session, user: User, month: date, assets: Decimal, debts: Decimal) -> None:
    item = db.scalar(
        select(NetWorthSnapshot).where(
            NetWorthSnapshot.user_id == user.id, NetWorthSnapshot.month == month
        )
    )
    if item is None:
        db.add(
            NetWorthSnapshot(user_id=user.id, month=month, assets=money(assets), debts=money(debts))
        )
    else:
        item.assets, item.debts = money(assets), money(debts)
    db.commit()


def snapshot_all(db: Session, today: date | None = None) -> int:
    """Rotina diária: atualiza a foto do mês de quem usa o app (para o gráfico mês a mês)."""
    count = 0
    for user in db.scalars(select(User).where(User.access_status == "approved")):
        overview(db, user, today)
        count += 1
    return count


def debt_weight(db: Session, user: User, income: Decimal) -> dict[str, Any] | None:
    """Peso das parcelas de dívidas na renda do mês (para o consultor)."""
    loans = [summary(db, loan) for loan in list_loans(db, user)]
    others = list_other(db, user)
    monthly = sum((s["next_payment"] or ZERO for s in loans), ZERO) + sum(
        (d.monthly_payment or ZERO for d in others), ZERO
    )
    if monthly <= 0 or income <= 0:
        return None
    return {"monthly": monthly, "pct": round(float(monthly / income * 100), 1)}
