"""v1.8: empréstimos a amigos com juros e parcelas, anotados na tela Divisões.

O cronograma é salvo parcela a parcela (LoanInstallment) e espelhado no Orçamento: quem me deve
vira receita prevista; quem eu devo vira despesa. O espelho é refeito a cada mudança (`sync`),
uma linha por mês do orçamento e por situação (recebido / a receber), para o mês não ficar
cheio de linhas quando o pagamento é por dia ou por semana.

Recebimentos: o valor informado preenche a parcela escolhida e, se sobrar, as seguintes (pagar
adiantado). Pagar menos deixa a parcela "parcial", com o que falta em aberto.
"""

from __future__ import annotations

import math
import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.months import month_of, today_local
from app.db.types import utcnow
from app.models import Expense, Income, LoanInstallment, LoanPayment, PersonalLoan, User
from app.services import loans_calc as calc

ZERO = Decimal("0")
CENT = Decimal("0.01")
MAX_LOANS = 200


def _name(person: str) -> str:
    name = " ".join(person.split())
    if not name:
        raise AppError(400, "invalid_person", "Informe o nome da pessoa.")
    return name[:60]


def _own(db: Session, user: User, loan_id: uuid.UUID) -> PersonalLoan:
    loan = db.get(PersonalLoan, loan_id)
    if loan is None or loan.user_id != user.id:
        raise AppError(404, "not_found", "Empréstimo não encontrado.")
    return loan


def installments(db: Session, loan: PersonalLoan) -> list[LoanInstallment]:
    return list(
        db.scalars(
            select(LoanInstallment)
            .where(LoanInstallment.loan_id == loan.id)
            .order_by(LoanInstallment.number)
        )
    )


def _received(item: LoanInstallment) -> Decimal:
    return item.received_amount or ZERO


def _open(item: LoanInstallment) -> Decimal:
    return max(item.amount - _received(item), ZERO)


# ---------------------------------------------------------------- simulação


def simulate(data: dict[str, Any]) -> dict[str, Any]:
    """Resultado da simulação: a taxa (dada ou calculada), o cronograma e as comparações."""
    principal = calc.cents(data["principal"])
    mode, frequency, count = data["mode"], data["frequency"], data["count"]
    first_due = data["first_due"]
    target = data.get("target", "rate")
    if mode == "none":
        rate = 0.0
    elif target == "rate":
        rate = float(data.get("rate") or 0)
    else:
        solved = calc.solve_rate(
            principal, mode, count, frequency, first_due, target, Decimal(str(data["value"]))
        )
        if solved is None:
            raise AppError(
                400,
                "impossible",
                "Não dá para chegar nesse valor com essa forma de juros. Confira o valor pedido.",
            )
        rate = solved
    result = calc.summary(principal, mode, rate, count, frequency, first_due)
    result["rate"] = round(rate, 4)
    result["compare"] = (
        calc.compare(principal, count, frequency, first_due, result["profit"])
        if result["profit"] > 0
        else []
    )
    result["market"] = None
    if data.get("market"):
        result["market"] = market(
            principal, result["profit"], result["schedule"], first_due, frequency
        )
    return result


def market(
    principal: Decimal,
    profit: Decimal,
    schedule: list[dict[str, Any]],
    first_due: date,
    frequency: str,
) -> dict[str, Any] | None:
    from app.services import indicators

    try:
        values = indicators.get_indicators()
    except Exception:  # sem indicadores, a comparação simplesmente não aparece
        return None
    cdi = (values.get("cdi") or {}).get("value")
    ipca = (values.get("ipca_12m") or {}).get("value")
    start = calc.start_date(first_due, frequency)  # type: ignore[arg-type]
    months = max((schedule[-1]["due_date"] - start).days, 1) / calc.MONTH_DAYS
    return calc.market(principal, profit, months, cdi, ipca)


# ---------------------------------------------------------------- criar, apagar


def create(db: Session, user: User, data: dict[str, Any]) -> PersonalLoan:
    count = db.query(PersonalLoan).filter(PersonalLoan.user_id == user.id).count()
    if count >= MAX_LOANS:
        raise AppError(400, "too_many", "Limite de empréstimos anotados atingido.")
    result = simulate({**data, "market": False})
    loan = PersonalLoan(
        user_id=user.id,
        person=_name(data["person"]),
        description=(data.get("description") or "").strip()[:120] or None,
        direction=data["direction"],
        principal=result["principal"],
        mode=data["mode"],
        rate=Decimal(str(result["rate"])).quantize(Decimal("0.0001")),
        frequency=data["frequency"],
        count=data["count"],
        first_due=data["first_due"],
        late_fee=data.get("late_fee"),
        late_interest=data.get("late_interest"),
    )
    db.add(loan)
    db.flush()
    # As parcelas saem da taxa exata (não da arredondada), para bater com a simulação.
    for row in result["schedule"]:
        db.add(
            LoanInstallment(
                loan_id=loan.id,
                number=row["number"],
                due_date=row["due_date"],
                amount=row["amount"],
                interest=row["interest"],
                principal_part=row["principal"],
            )
        )
    db.flush()
    sync(db, user, loan)
    db.commit()
    return loan


def remove(db: Session, user: User, loan_id: uuid.UUID, *, commit: bool = True) -> None:
    """Apaga o empréstimo. O que já foi recebido continua no Orçamento (vira lançamento comum);
    o que ainda estava previsto sai."""
    loan = _own(db, user, loan_id)
    received = {i.number for i in installments(db, loan) if _received(i) > 0}
    for model in (Income, Expense):
        for item in db.scalars(select(model).where(model.personal_loan_id == loan.id)):
            if received and _is_received_line(item):
                item.personal_loan_id = None
            else:
                db.delete(item)
    db.execute(delete(LoanPayment).where(LoanPayment.loan_id == loan.id))
    db.execute(delete(LoanInstallment).where(LoanInstallment.loan_id == loan.id))
    db.delete(loan)
    if commit:
        db.commit()
    else:
        db.flush()


def _is_received_line(item: Income | Expense) -> bool:
    if isinstance(item, Expense):
        return bool(item.paid)
    return (item.notes or "").startswith("Recebido")


# ---------------------------------------------------------------- receber, desfazer, quitar


def _apply(
    items: list[LoanInstallment],
    number: int,
    amount: Decimal,
    on: date,
    mode: str,
    discount: bool,
) -> tuple[list[list[str]], Decimal]:
    """Distribui um pagamento nas parcelas. Devolve [[parcela, valor, juros descontados]] e o
    desconto total. "next": em ordem a partir de `number`; "end": completa `number` e o resto
    paga as últimas (de trás para frente), com desconto opcional dos juros dessas."""
    left = amount
    allocation: dict[int, list[Decimal]] = {}
    saved = ZERO

    def pay(item: LoanInstallment, cut_interest: bool) -> None:
        nonlocal left, saved
        if left <= 0 or _open(item) <= 0:
            return
        cut = ZERO
        if cut_interest and item.due_date > on and item.amount:
            # Juros proporcionais ao que falta, só quando o valor cobre a parcela inteira.
            cut = calc.cents(item.interest * _open(item) / item.amount)
            if _open(item) - cut > left:
                cut = ZERO
            item.amount -= cut
            item.interest -= cut
            saved += cut
        part = min(left, _open(item))
        item.received_amount = _received(item) + part
        item.received_at = on
        left -= part
        entry = allocation.setdefault(item.number, [ZERO, ZERO])
        entry[0] += part
        entry[1] += cut

    ordered = [i for i in items if i.number >= number]
    if mode == "end":
        first = next(i for i in ordered if i.number == number)
        pay(first, False)
        for item in reversed(ordered):
            if item.number != number:
                pay(item, discount)
    else:
        for item in ordered:
            pay(item, mode == "payoff" and discount)
    return [[n, str(v), str(c)] for n, (v, c) in sorted(allocation.items())], saved


def receive(
    db: Session,
    user: User,
    loan_id: uuid.UUID,
    number: int,
    amount: Decimal | None,
    on: date | None,
    mode: str = "next",
    discount: bool = False,
    preview: bool = False,
) -> PersonalLoan | dict[str, Any]:
    """Registra um pagamento a partir da parcela `number`. Sem valor = a parcela inteira.
    Com `preview`, devolve como ficaria (sem salvar)."""
    loan = _own(db, user, loan_id)
    if loan.settled_at:
        raise AppError(400, "settled", "Este empréstimo já foi quitado.")
    items = installments(db, loan)
    start = next((i for i in items if i.number == number), None)
    if start is None:
        raise AppError(404, "not_found", "Parcela não encontrada.")
    if _open(start) <= 0:
        raise AppError(400, "already_paid", "Essa parcela já foi paga.")
    on = on or today_local()
    value = calc.cents(amount) if amount is not None else _open(start)
    open_total = sum((_open(i) for i in items if i.number >= number), ZERO)
    if value <= 0:
        raise AppError(400, "invalid_amount", "Informe um valor maior que zero.")
    if value > open_total:
        raise AppError(
            400,
            "too_much",
            "O valor passa do que falta pagar. Use “Quitar antecipado” para encerrar.",
        )
    allocation, saved = _apply(items, number, value, on, mode, discount)
    if all(_open(i) <= 0 for i in items):
        loan.settled_at = utcnow()
    if preview:
        db.flush()
        out = detail(db, loan)
        db.rollback()
        return out
    db.add(
        LoanPayment(
            loan_id=loan.id,
            paid_on=on,
            amount=value,
            mode=mode,
            discount=saved,
            allocation=allocation,
        )
    )
    sync(db, user, loan)
    db.commit()
    return loan


def payments(db: Session, loan: PersonalLoan) -> list[LoanPayment]:
    return list(
        db.scalars(
            select(LoanPayment)
            .where(LoanPayment.loan_id == loan.id)
            .order_by(LoanPayment.paid_on.desc(), LoanPayment.created_at.desc())
        )
    )


def undo(db: Session, user: User, loan_id: uuid.UUID, payment_id: uuid.UUID) -> PersonalLoan:
    """Desfaz um pagamento: tira o valor das parcelas e devolve os juros descontados."""
    loan = _own(db, user, loan_id)
    payment = db.get(LoanPayment, payment_id)
    if payment is None or payment.loan_id != loan.id:
        raise AppError(404, "not_found", "Pagamento não encontrado.")
    if loan.rescheduled_at and payment.created_at <= loan.rescheduled_at:
        raise AppError(
            400,
            "locked",
            "Esse pagamento é de antes das parcelas serem refeitas e não pode ser desfeito.",
        )
    items = {i.number: i for i in installments(db, loan)}
    for number, value, cut in payment.allocation:
        item = items.get(int(number))
        if item is None:
            continue
        got = _received(item) - Decimal(value)
        item.received_amount = got if got > 0 else None
        item.amount += Decimal(cut)
        item.interest += Decimal(cut)
    db.delete(payment)
    db.flush()
    # A data de recebimento de cada parcela volta a ser a do último pagamento que a tocou.
    last: dict[int, date] = {}
    for other in sorted(payments(db, loan), key=lambda x: (x.paid_on, x.created_at)):
        for number, _, _ in other.allocation:
            last[int(number)] = other.paid_on
    for item in items.values():
        item.received_at = last.get(item.number) if item.received_amount else None
    loan.settled_at = None if any(_open(i) > 0 for i in items.values()) else loan.settled_at
    sync(db, user, loan)
    db.commit()
    return loan


def payoff_quote(db: Session, loan: PersonalLoan, on: date, discount: bool) -> dict[str, Any]:
    """Quanto falta para quitar hoje. Com desconto, saem os juros das parcelas que ainda não
    venceram (o justo para quem paga adiantado)."""
    items = installments(db, loan)
    remaining = sum((_open(i) for i in items), ZERO)
    saved = ZERO
    if discount:
        for i in items:
            if i.due_date > on and _open(i) > 0:
                # Juros proporcionais ao que ainda falta da parcela.
                saved += calc.cents(i.interest * _open(i) / i.amount) if i.amount else ZERO
    return {"remaining": remaining, "discount": saved, "value": remaining - saved}


def payoff(
    db: Session, user: User, loan_id: uuid.UUID, on: date | None, discount: bool
) -> PersonalLoan:
    loan = _own(db, user, loan_id)
    if loan.settled_at:
        raise AppError(400, "settled", "Este empréstimo já foi quitado.")
    on = on or today_local()
    items = installments(db, loan)
    first = next((i for i in items if _open(i) > 0), None)
    if first is None:
        raise AppError(400, "settled", "Este empréstimo já foi quitado.")
    value = payoff_quote(db, loan, on, discount)["value"]
    allocation, saved = _apply(items, first.number, value + ZERO, on, "payoff", discount)
    # Centavos de arredondamento: o que ainda restar fica quitado junto.
    for item in items:
        if _open(item) > 0:
            extra = _open(item)
            item.received_amount = _received(item) + extra
            item.received_at = on
            value += extra
            allocation.append([item.number, str(extra), "0"])
    db.add(
        LoanPayment(
            loan_id=loan.id,
            paid_on=on,
            amount=value,
            mode="payoff",
            discount=saved,
            allocation=allocation,
        )
    )
    loan.settled_at = utcnow()
    sync(db, user, loan)
    db.commit()
    return loan


def reschedule(
    db: Session, user: User, loan_id: uuid.UUID, amount: Decimal, preview: bool = False
) -> PersonalLoan | dict[str, Any]:
    """Novo valor por pagamento: o que falta é redividido nesse valor, na mesma frequência, a
    partir da próxima parcela em aberto. O que já foi pago não muda."""
    loan = _own(db, user, loan_id)
    if loan.settled_at:
        raise AppError(400, "settled", "Este empréstimo já foi quitado.")
    amount = calc.cents(amount)
    if amount <= 0:
        raise AppError(400, "invalid_amount", "Informe um valor maior que zero.")
    items = installments(db, loan)
    pending = [i for i in items if _open(i) > 0]
    if not pending:
        raise AppError(400, "settled", "Não há parcelas em aberto.")
    total = sum((_open(i) for i in pending), ZERO)
    interest = sum(
        (calc.cents(i.interest * _open(i) / i.amount) if i.amount else ZERO for i in pending), ZERO
    )
    first = pending[0]
    start_due = first.due_date
    skip_first = _received(first) > 0
    # Parcelas pagas em parte ficam fechadas com o que já receberam; o resto entra na divisão.
    for item in pending:
        if _received(item) > 0:
            paid_share = _received(item) / item.amount if item.amount else ZERO
            item.interest = calc.cents(item.interest * paid_share)
            item.amount = _received(item)
            item.principal_part = item.amount - item.interest
        else:
            db.delete(item)
    db.flush()
    count = math.ceil(total / amount)
    dates = calc.due_dates(start_due, count + (1 if skip_first else 0), loan.frequency)  # type: ignore[arg-type]
    if skip_first:
        dates = dates[1:]
    top = max((i.number for i in items), default=0)
    rest_interest = interest
    for index in range(count):
        value = amount if index < count - 1 else total - amount * (count - 1)
        share = calc.cents(interest * value / total) if index < count - 1 else rest_interest
        rest_interest -= share
        db.add(
            LoanInstallment(
                loan_id=loan.id,
                number=top + 1000 + index,
                due_date=dates[index],
                amount=value,
                interest=share,
                principal_part=value - share,
            )
        )
    db.flush()
    # Numera de novo pela data (as fechadas mantêm a posição delas).
    final = sorted(installments(db, loan), key=lambda i: (i.due_date, i.number))
    for index, item in enumerate(final):
        item.number = 10000 + index
    db.flush()
    for index, item in enumerate(final, start=1):
        item.number = index
    loan.count = len(final)
    loan.rescheduled_at = utcnow()
    db.flush()
    if preview:
        out = detail(db, loan)
        db.rollback()
        return out
    sync(db, user, loan)
    db.commit()
    return loan


def set_phone(db: Session, user: User, loan_id: uuid.UUID, phone: str | None) -> PersonalLoan:
    loan = _own(db, user, loan_id)
    digits = "".join(c for c in (phone or "") if c.isdigit())
    loan.phone = digits[:20] or None
    db.commit()
    return loan


# ---------------------------------------------------------------- espelho no Orçamento


def _label(loan: PersonalLoan, numbers: list[int]) -> str:
    who = f"Empréstimo · {loan.person}"
    if len(numbers) == 1:
        return f"{who} · {numbers[0]}/{loan.count}"[:120]
    return f"{who} · {len(numbers)} pagamentos"[:120]


def sync(db: Session, user: User, loan: PersonalLoan) -> None:
    """Refaz as receitas (ou despesas) do empréstimo no Orçamento."""
    for model in (Income, Expense):
        db.execute(delete(model).where(model.personal_loan_id == loan.id))
    start_day = user.month_start_day
    # (mês, recebido?) → [(parcela, data, valor)]
    groups: dict[tuple[date, bool], list[tuple[int, date, Decimal]]] = defaultdict(list)
    for item in installments(db, loan):
        got = _received(item)
        if got > 0 and item.received_at:
            groups[(month_of(item.received_at, start_day), True)].append(
                (item.number, item.received_at, got)
            )
        rest = _open(item)
        if rest > 0 and not loan.settled_at:
            groups[(month_of(item.due_date, start_day), False)].append(
                (item.number, item.due_date, rest)
            )
    for (month, done), rows in sorted(groups.items()):
        numbers = sorted({n for n, _, _ in rows})
        amount = sum((v for _, _, v in rows), ZERO)
        last = max(d for _, d, _ in rows)
        label = _label(loan, numbers)
        if loan.direction == "owes_me":
            db.add(
                Income(
                    user_id=user.id,
                    month=month,
                    description=label,
                    amount=amount,
                    income_type="variable",
                    day=last.day if len(rows) == 1 else None,
                    notes="Recebido" if done else "Previsto (empréstimo na tela Divisões)",
                    personal_loan_id=loan.id,
                )
            )
        else:
            db.add(
                Expense(
                    user_id=user.id,
                    month=month,
                    description=label,
                    amount=amount,
                    due_date=last if not done else min(d for _, d, _ in rows),
                    paid=done,
                    paid_at=utcnow() if done else None,
                    personal_loan_id=loan.id,
                )
            )
    db.flush()


# ---------------------------------------------------------------- leitura


def status_of(item: LoanInstallment, today: date) -> str:
    if _open(item) <= 0:
        return "paid"
    if item.due_date < today:
        return "late"
    return "partial" if _received(item) > 0 else "open"


def detail(db: Session, loan: PersonalLoan, today: date | None = None) -> dict[str, Any]:
    today = today or today_local()
    items = installments(db, loan)
    fee = float(loan.late_fee) if loan.late_fee is not None else None
    late_rate = float(loan.late_interest) if loan.late_interest is not None else None
    rows = []
    late_count, late_amount = 0, ZERO
    for i in items:
        status = status_of(i, today)
        charge = ZERO
        if status == "late":
            charge = calc.late_charge(_open(i), (today - i.due_date).days, fee, late_rate)
            late_count += 1
            late_amount += _open(i) + charge
        rows.append(
            {
                "number": i.number,
                "due_date": i.due_date,
                "amount": i.amount,
                "interest": i.interest,
                "principal": i.principal_part,
                "received_amount": i.received_amount,
                "received_at": i.received_at,
                "open": _open(i),
                "status": status,
                "late_charge": charge,
            }
        )
    total = sum((i.amount for i in items), ZERO)
    received = sum((min(_received(i), i.amount) for i in items), ZERO)
    interest = sum((i.interest for i in items), ZERO)
    interest_received = sum(
        (
            calc.cents(i.interest * min(_received(i), i.amount) / i.amount)
            for i in items
            if i.amount
        ),
        ZERO,
    )
    next_item = next((r for r in rows if r["status"] != "paid"), None)
    sched = [
        calc.Row(i.number, i.due_date, i.amount, i.interest, i.principal_part, ZERO) for i in items
    ]
    monthly = calc.equivalent_monthly(loan.principal, sched, loan.frequency)  # type: ignore[arg-type]
    paid_count = sum(1 for r in rows if r["status"] == "paid")
    return {
        "id": loan.id,
        "person": loan.person,
        "description": loan.description,
        "direction": loan.direction,
        "principal": loan.principal,
        "mode": loan.mode,
        "rate": loan.rate,
        "frequency": loan.frequency,
        "count": loan.count,
        "first_due": loan.first_due,
        "late_fee": loan.late_fee,
        "late_interest": loan.late_interest,
        "created_at": loan.created_at,
        "settled_at": loan.settled_at,
        "total": total,
        "received": received,
        "remaining": sum((r["open"] for r in rows), ZERO) if not loan.settled_at else CENT * 0,
        "profit": interest,
        "profit_received": interest_received,
        "paid_count": paid_count,
        "late_count": late_count,
        "late_amount": late_amount,
        "next": next_item,
        "monthly_equivalent": round(monthly, 4),
        "yearly_equivalent": round(((1 + monthly / 100) ** 12 - 1) * 100, 2),
        "payback": calc.payback(sched, loan.principal),
        "installments": rows,
        "phone": loan.phone,
        "payments": [
            {
                "id": p.id,
                "paid_on": p.paid_on,
                "amount": p.amount,
                "mode": p.mode,
                "discount": p.discount,
                "numbers": [int(n) for n, _, _ in p.allocation],
                "can_undo": not (loan.rescheduled_at and p.created_at <= loan.rescheduled_at),
            }
            for p in payments(db, loan)
        ],
        "last_due": items[-1].due_date if items else None,
    }


def all_loans(db: Session, user: User, today: date | None = None) -> list[dict[str, Any]]:
    loans = db.scalars(
        select(PersonalLoan)
        .where(PersonalLoan.user_id == user.id)
        .order_by(PersonalLoan.created_at.desc())
    )
    return [detail(db, loan, today) for loan in loans]


def totals(loans: list[dict[str, Any]]) -> dict[str, Any]:
    """Números do topo da tela: o que está emprestado com juros e o lucro."""
    lent = [x for x in loans if x["direction"] == "owes_me"]
    active = [x for x in lent if not x["settled_at"]]
    principal = sum((x["principal"] for x in active), ZERO)
    weighted = sum(x["yearly_equivalent"] * float(x["principal"]) for x in active)
    return {
        "lent": principal,
        "lent_count": len(active),
        "to_receive": sum((x["remaining"] for x in active), ZERO),
        "profit_expected": sum((x["profit"] for x in active), ZERO),
        "profit_received": sum((x["profit_received"] for x in lent), ZERO),
        "yearly": round(weighted / float(principal), 2) if principal else None,
        "late_count": sum(x["late_count"] for x in loans),
    }


def find_person(loans: list[dict[str, Any]], person: str) -> list[dict[str, Any]]:
    key = " ".join(person.split()).casefold()
    return [x for x in loans if x["person"].casefold() == key]
