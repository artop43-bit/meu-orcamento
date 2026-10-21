"""Relatório para o Imposto de Renda (v1.4): o ano organizado na ordem das fichas da declaração.

- Pagamentos dedutíveis: despesas das categorias marcadas como saúde, educação, previdência
  privada (PGBL) ou pensão alimentícia, uma a uma, com data e descrição.
- Rendimentos: receitas do ano por tipo (fixas, variáveis e faturamento do MEI).
- Bens e direitos em 31/12: investimentos pelo valor aplicado (custo, como pede a declaração)
  e saldos das contas calculados pelo app.
- Dívidas e ônus em 31/12: saldo devedor dos financiamentos depois das parcelas que venceram
  até 31/12 e as outras dívidas com o saldo informado.

É um apoio para preencher a declaração; não substitui os informes do banco e da empresa.
"""

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category, Expense, Income, Investment, User
from app.services import loans, money

ZERO = Decimal("0")
DEDUCTIBLE = {
    "saude": "Saúde (médicos, dentistas, exames, hospitais, plano de saúde)",
    "educacao": "Educação (escola, faculdade, pós; tem teto anual por pessoa)",
    "previdencia": "Previdência privada PGBL (até 12% da renda tributável)",
    "pensao": "Pensão alimentícia judicial",
}


def report(db: Session, user: User, year: int) -> dict[str, Any]:
    start, end = date(year, 1, 1), date(year, 12, 1)
    categories = {c.id: c for c in db.scalars(select(Category).where(Category.user_id == user.id))}
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in db.scalars(
        select(Expense)
        .where(Expense.user_id == user.id, Expense.month >= start, Expense.month <= end)
        .order_by(Expense.due_date, Expense.created_at)
    ):
        category = categories.get(e.category_id) if e.category_id else None
        if category is None or not category.deductible:
            continue
        groups[category.deductible].append(
            {
                "date": e.purchase_date or e.due_date or e.month,
                "description": e.description,
                "category": category.name,
                "amount": e.amount,
            }
        )
    deductions = [
        {
            "kind": kind,
            "label": label,
            "total": sum((i["amount"] for i in groups[kind]), ZERO),
            "items": groups[kind],
        }
        for kind, label in DEDUCTIBLE.items()
        if groups[kind]
    ]

    incomes: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for i in db.scalars(
        select(Income).where(Income.user_id == user.id, Income.month >= start, Income.month <= end)
    ):
        incomes["mei" if i.mei else (i.income_type or "fixed")] += i.amount
    income_rows = [
        {"kind": kind, "label": label, "total": incomes[kind]}
        for kind, label in (
            ("fixed", "Rendimentos fixos (salário, aposentadoria, aluguéis)"),
            ("variable", "Rendimentos variáveis (freelances, comissões, outros)"),
            ("mei", "Faturamento do MEI (declarado à parte, na DASN-SIMEI)"),
        )
        if incomes[kind]
    ]

    year_end = date(year, 12, 31)
    assets = [
        {"description": f"{inv.name} ({inv.kind})", "value": inv.invested_amount}
        for inv in db.scalars(select(Investment).where(Investment.user_id == user.id))
        if inv.created_at.date() <= year_end
    ]
    for row in money.balances(db, user, today=year_end):
        account = row["account"]
        if account.kind != "benefit" and row["balance"] > 0:
            assets.append({"description": f"Saldo em {account.name}", "value": row["balance"]})

    debts = []
    for loan in loans.list_loans(db, user):
        rows = loans.loan_rows(loan)
        due = [r for r in rows if loans.due_for(loan, r.number) <= year_end]
        if not due and loan.first_due > year_end:
            balance = loan.principal + (loan.iof or ZERO)
        else:
            balance = due[-1].balance if due else loan.principal
        if balance > 0:
            debts.append(
                {
                    "description": f"{loan.name} ({loan.institution or 'financiamento'})",
                    "value": balance,
                }
            )
    for other in loans.list_other(db, user):
        if other.balance > 0:
            debts.append({"description": other.name, "value": other.balance})

    return {
        "year": year,
        "deductions": deductions,
        "deductions_total": sum((d["total"] for d in deductions), ZERO),
        "incomes": income_rows,
        "assets": assets,
        "debts": debts,
    }
