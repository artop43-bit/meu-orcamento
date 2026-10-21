"""Raio-x do dinheiro que escapa (v1.4).

- Tarifas e juros: o que foi pago no ano em tarifas e pacotes de serviço, anuidades, IOF,
  juros e encargos e multas, encontrado pela descrição das despesas; mais os juros embutidos nas
  parcelas pagas dos financiamentos (pela tabela de cada contrato).
- Inflação pessoal: quanto subiram os gastos de cada categoria nos últimos 12 meses contra os
  12 meses anteriores, comparado com o IPCA acumulado em 12 meses.
"""

import re
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.months import add_months, month_of, today_local
from app.models import Category, Expense, User
from app.services import loans
from app.services.suggest import normalize

ZERO = Decimal("0")

FEES: list[tuple[str, str, re.Pattern[str]]] = [
    ("anuidade", "Anuidades", re.compile(r"\banuidade")),
    ("iof", "IOF", re.compile(r"\biof\b")),
    ("multa", "Multas e mora", re.compile(r"\bmulta\b|\bmora\b|atraso")),
    (
        "juros",
        "Juros e encargos",
        re.compile(r"\bjuros?\b|encargo|rotativo|cheque especial|\bcet\b|parcelamento de fatura"),
    ),
    (
        "tarifa",
        "Tarifas e pacotes",
        re.compile(
            r"\btarifa|\bcesta\b|pacote de servi|manutencao de conta|\btaxa\b|\bted\b|\bdoc\b"
        ),
    ),
]


def fees(db: Session, user: User, year: int) -> dict[str, Any]:
    start, end = date(year, 1, 1), date(year, 12, 1)
    totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    expenses = list(
        db.scalars(
            select(Expense).where(
                Expense.user_id == user.id, Expense.month >= start, Expense.month <= end
            )
        )
    )
    for e in expenses:
        if e.loan_id:
            continue
        text = normalize(e.description)
        for key, _, pattern in FEES:
            if pattern.search(text):
                totals[key] += e.amount
                if len(examples[key]) < 5:
                    examples[key].append({"description": e.description, "amount": e.amount})
                break
    # Juros dentro das parcelas pagas dos financiamentos (pela tabela do contrato).
    loan_interest = ZERO
    for loan in loans.list_loans(db, user):
        rows = {r.number: r for r in loans.loan_rows(loan)}
        for e in expenses:
            if e.loan_id == loan.id and e.paid and e.installment_number in rows:
                loan_interest += rows[e.installment_number].interest
    groups = [
        {"key": key, "label": label, "total": totals[key], "examples": examples[key]}
        for key, label, _ in FEES
        if totals[key] > 0
    ]
    if loan_interest > 0:
        groups.append(
            {
                "key": "financiamentos",
                "label": "Juros nas parcelas dos financiamentos",
                "total": loan_interest.quantize(Decimal("0.01")),
                "examples": [],
            }
        )
    return {
        "year": year,
        "groups": sorted(groups, key=lambda g: g["total"], reverse=True),
        "total": sum((g["total"] for g in groups), ZERO),
    }


def personal_inflation(db: Session, user: User) -> dict[str, Any]:
    from app.services import indicators

    current = month_of(today_local(), user.month_start_day)
    recent_start = add_months(current, -12)
    previous_start = add_months(current, -24)
    names = {c.id: c.name for c in db.scalars(select(Category).where(Category.user_id == user.id))}
    recent: dict[Any, Decimal] = defaultdict(lambda: ZERO)
    previous: dict[Any, Decimal] = defaultdict(lambda: ZERO)
    for e in db.scalars(
        select(Expense).where(
            Expense.user_id == user.id,
            Expense.month >= previous_start,
            Expense.month < current,
            Expense.loan_id.is_(None),
            Expense.installment_group_id.is_(None),
        )
    ):
        (recent if e.month >= recent_start else previous)[e.category_id] += e.amount
    rows = []
    for category_id, before in previous.items():
        now = recent.get(category_id, ZERO)
        if before <= 0 or now <= 0:
            continue
        rows.append(
            {
                "category_id": category_id,
                "name": names.get(category_id, "Sem categoria") if category_id else "Sem categoria",
                "before": before,
                "now": now,
                "change_pct": round(float((now - before) / before * 100), 1),
            }
        )
    rows.sort(key=lambda r: r["now"], reverse=True)
    total_before = sum((r["before"] for r in rows), ZERO)
    total_now = sum((r["now"] for r in rows), ZERO)
    ipca = (indicators.get_indicators() or {}).get("ipca_12m")
    return {
        "categories": rows[:10],
        "total_change_pct": round(float((total_now - total_before) / total_before * 100), 1)
        if total_before > 0
        else None,
        "ipca_12m": ipca["value"] if ipca else None,
        "period": {"from": recent_start, "to": add_months(current, -1)},
    }
