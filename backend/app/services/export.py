"""Exportação: lançamentos em CSV, Excel ou PDF (v1.7.6.1) e backup completo em JSON."""

import csv
import io
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.months import format_month
from app.models import (
    Category,
    CreditCard,
    Expense,
    Goal,
    Income,
    Investment,
    Loan,
    MoneyAccount,
    OtherDebt,
    PersonalLoan,
    RecurringItem,
    SplitShare,
    SupportMessage,
    SupportThread,
    User,
)
from app.services import budget

COLUMNS = [
    "Mês",
    "Tipo",
    "Data",
    "Descrição",
    "Categoria",
    "Conta ou cartão",
    "Forma de pagamento",
    "Valor",
    "Pago",
    "Parcela",
    "Recorrente",
]
PAYMENT = {
    "pix": "Pix",
    "debit": "Débito",
    "credit": "Crédito",
    "boleto": "Boleto",
    "cash": "Dinheiro",
}


@dataclass
class Filters:
    """Recorte da exportação: o que entra (tudo, despesas ou receitas) e de onde."""

    kind: str = "all"  # all | expense | income
    category_ids: set[uuid.UUID] = field(default_factory=set)
    account_ids: set[uuid.UUID] = field(default_factory=set)
    card_ids: set[uuid.UUID] = field(default_factory=set)


def transactions(
    db: Session, user: User, start: date, end: date, filters: Filters | None = None
) -> list[dict[str, Any]]:
    filters = filters or Filters()
    categories = {c.id: c.name for c in budget.list_categories(db, user)}
    accounts = {
        a.id: a.name
        for a in db.scalars(select(MoneyAccount).where(MoneyAccount.user_id == user.id))
    }
    cards = {
        c.id: c.name for c in db.scalars(select(CreditCard).where(CreditCard.user_id == user.id))
    }
    place_filter = filters.account_ids | filters.card_ids
    rows: list[dict[str, Any]] = []
    if filters.kind in ("all", "income") and not filters.category_ids and not filters.card_ids:
        for income in db.scalars(
            select(Income)
            .where(Income.user_id == user.id, Income.month.between(start, end))
            .order_by(Income.month, Income.created_at)
        ):
            if filters.account_ids and income.account_id not in filters.account_ids:
                continue
            rows.append(
                {
                    "month": income.month,
                    "type": "Receita",
                    "date": income.month.replace(day=min(income.day, 28)) if income.day else None,
                    "description": income.description,
                    "category": "",
                    "place": accounts.get(income.account_id, "") if income.account_id else "",
                    "payment": "",
                    "amount": income.amount,
                    "paid": None,
                    "installment": "",
                    "recurring": income.recurring_id is not None,
                }
            )
    if filters.kind in ("all", "expense"):
        for expense in db.scalars(
            select(Expense)
            .where(Expense.user_id == user.id, Expense.month.between(start, end))
            .order_by(Expense.month, Expense.due_date, Expense.created_at)
        ):
            if filters.category_ids and expense.category_id not in filters.category_ids:
                continue
            card_id = expense.card_id or expense.debit_card_id
            if (
                place_filter
                and expense.account_id not in place_filter
                and card_id not in place_filter
            ):
                continue
            place = cards.get(card_id, "") if card_id else accounts.get(expense.account_id, "")
            rows.append(
                {
                    "month": expense.month,
                    "type": "Despesa",
                    "date": expense.due_date,
                    "description": expense.description,
                    "category": categories.get(expense.category_id, "")
                    if expense.category_id
                    else "",
                    "place": place or "",
                    "payment": PAYMENT.get(expense.payment_method or "", ""),
                    "amount": -expense.amount,
                    "paid": expense.paid,
                    "installment": (
                        f"{expense.installment_number}/{expense.installment_total}"
                        if expense.installment_total
                        else ""
                    ),
                    "recurring": expense.recurring_id is not None,
                }
            )
    rows.sort(key=lambda r: (r["month"], r["type"] != "Receita", r["date"] or date.max))
    return rows


def by_category(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    totals: dict[str, Decimal] = {}
    for r in rows:
        if r["type"] == "Despesa":
            name = r["category"] or "Sem categoria"
            totals[name] = totals.get(name, Decimal("0")) + abs(r["amount"])
    grand = sum(totals.values(), Decimal("0"))
    return [
        {"name": name, "total": total, "share": float(total / grand) if grand else 0.0}
        for name, total in sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    ]


def describe_filters(
    db: Session, user: User, start: date, end: date, filters: Filters
) -> list[tuple[str, str]]:
    """O recorte em palavras, para o cabeçalho do PDF."""
    from app.services.pdf_export import period_label

    kind = {"all": "Receitas e despesas", "expense": "Só despesas", "income": "Só receitas"}
    lines = [("Período", period_label(start, end)), ("Conteúdo", kind[filters.kind])]
    places = [
        a.name
        for a in db.scalars(select(MoneyAccount).where(MoneyAccount.user_id == user.id))
        if a.id in filters.account_ids
    ] + [
        c.name
        for c in db.scalars(select(CreditCard).where(CreditCard.user_id == user.id))
        if c.id in filters.card_ids
    ]
    lines.append(("Contas e cartões", ", ".join(sorted(places)) if places else "Todos"))
    if filters.kind != "income":
        names = [c.name for c in budget.list_categories(db, user) if c.id in filters.category_ids]
        lines.append(("Categorias", ", ".join(sorted(names)) if names else "Todas"))
    if filters.kind == "all" and (filters.category_ids or filters.card_ids):
        lines.append(("Observação", "Com categoria ou cartão escolhidos, só entram despesas."))
    return lines


def _yes_no(value: bool | None) -> str:
    return "" if value is None else ("Sim" if value else "Não")


def to_csv(rows: list[dict[str, Any]]) -> bytes:
    """CSV no padrão do Excel brasileiro: separador ";", vírgula decimal e BOM UTF-8."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(COLUMNS)
    for r in rows:
        writer.writerow(
            [
                format_month(r["month"]),
                r["type"],
                r["date"].strftime("%d/%m/%Y") if r["date"] else "",
                r["description"],
                r["category"],
                r["place"],
                r["payment"],
                f"{r['amount']:.2f}".replace(".", ","),
                _yes_no(r["paid"]),
                r["installment"],
                _yes_no(r["recurring"]),
            ]
        )
    return ("﻿" + buffer.getvalue()).encode("utf-8")


def to_xlsx(rows: list[dict[str, Any]], summary: list[dict[str, Any]]) -> bytes:
    workbook = Workbook()
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="1F6F5C")
    money_format = '"R$" #,##0.00;[Red]-"R$" #,##0.00'

    def header(sheet: Any, names: list[str]) -> None:
        sheet.append(names)
        for cell in sheet[1]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center")
        sheet.freeze_panes = "A2"

    sheet = workbook.active
    sheet.title = "Lançamentos"
    header(sheet, COLUMNS)
    for r in rows:
        sheet.append(
            [
                format_month(r["month"]),
                r["type"],
                r["date"],
                r["description"],
                r["category"],
                r["place"],
                r["payment"],
                float(r["amount"]),
                _yes_no(r["paid"]),
                r["installment"],
                _yes_no(r["recurring"]),
            ]
        )
    for row in sheet.iter_rows(min_row=2):
        row[2].number_format = "DD/MM/YYYY"
        row[7].number_format = money_format
    sheet.auto_filter.ref = sheet.dimensions
    for index, width in enumerate([10, 10, 12, 40, 18, 20, 12, 15, 7, 9, 11], start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width

    resume = workbook.create_sheet("Resumo mensal")
    header(resume, ["Mês", "Receitas", "Despesas", "Pago", "Resultado", "% comprometido"])
    for point in summary:
        resume.append(
            [
                format_month(point["month"]),
                float(point["income"]),
                float(point["expenses"]),
                float(point["paid"]),
                float(point["balance"]),
                point["committed_pct"] / 100 if point["committed_pct"] is not None else None,
            ]
        )
    for row in resume.iter_rows(min_row=2):
        for cell in row[1:5]:
            cell.number_format = money_format
        row[5].number_format = "0.0%"
    for index, width in enumerate([10, 15, 15, 15, 15, 15], start=1):
        resume.column_dimensions[get_column_letter(index)].width = width

    categories = workbook.create_sheet("Por categoria")
    header(categories, ["Categoria", "Total", "% das despesas"])
    for item in by_category(rows):
        categories.append([item["name"], float(item["total"]), item["share"]])
    for row in categories.iter_rows(min_row=2):
        row[1].number_format = money_format
        row[2].number_format = "0.0%"
    for index, width in enumerate([24, 16, 16], start=1):
        categories.column_dimensions[get_column_letter(index)].width = width

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def annual(db: Session, user: User, year: int) -> dict[str, Any]:
    """Resumo do ano (para o relatório anual em PDF): totais, meses e categorias."""
    start, end = date(year, 1, 1), date(year, 12, 1)
    months = period_summary(db, user, start, end)
    rows = transactions(db, user, start, end)
    income = sum((m["income"] for m in months), Decimal("0"))
    expenses = sum((m["expenses"] for m in months), Decimal("0"))
    investments = list(db.scalars(select(Investment).where(Investment.user_id == user.id)))
    goals = list(db.scalars(select(Goal).where(Goal.user_id == user.id)))
    from app.services import taxreport

    return {
        # v1.4: relatório para o Imposto de Renda (deduções, rendimentos, bens e dívidas).
        "tax": taxreport.report(db, user, year),
        "year": year,
        "income": income,
        "expenses": expenses,
        "balance": income - expenses,
        "savings_rate": round(float((income - expenses) / income * 100), 1) if income > 0 else None,
        "months": months,
        "by_category": by_category(rows),
        "investments_total": sum((i.current_value for i in investments), Decimal("0")),
        "goals": [
            {
                "name": g.name,
                "target_amount": g.target_amount,
                "current_amount": g.current_amount,
                "completed": g.completed_at is not None,
            }
            for g in goals
        ],
    }


def months_between(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + end.month - start.month + 1


def period_summary(db: Session, user: User, start: date, end: date) -> list[dict[str, Any]]:
    return budget.history(db, user, end, months_between(start, end))


# ---------------------------------------------------------------- backup completo


def _serialize(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def _rows(
    db: Session, model: Any, user: User, skip: set[str] | None = None
) -> list[dict[str, Any]]:
    skip = (skip or set()) | {"user_id"}
    columns = [c.key for c in model.__table__.columns if c.key not in skip]
    return [
        {column: _serialize(getattr(item, column)) for column in columns}
        for item in db.scalars(select(model).where(model.user_id == user.id))
    ]


def backup(db: Session, user: User) -> dict[str, Any]:
    """Todos os dados do usuário, em formato legível por máquina (portabilidade, LGPD art. 18)."""
    return {
        "format": "meu-orcamento-backup",
        "version": 1,
        "exported_at": datetime.now(UTC).isoformat(),
        "account": {
            "email": user.email,
            "created_at": user.created_at.isoformat(),
            "two_factor_enabled": user.totp_enabled,
        },
        "profile": {
            "display_name": user.display_name,
            "bio": user.bio,
            "city": user.city,
            "profession": user.profession,
        },
        "categories": _rows(db, Category, user),
        "recurring": _rows(db, RecurringItem, user),
        "incomes": _rows(db, Income, user),
        "expenses": _rows(db, Expense, user),
        "goals": _rows(db, Goal, user),
        "investments": _rows(db, Investment, user),
        "cards": _rows(db, CreditCard, user),
        "accounts": _rows(db, MoneyAccount, user),
        "loans": _rows(db, Loan, user),
        "other_debts": _rows(db, OtherDebt, user),
        "splits": _rows(db, SplitShare, user),
        "friend_loans": _friend_loans(db, user),
        "support_requests": _support(db, user),
        "ask_conversations": _ask(db, user),
    }


def _friend_loans(db: Session, user: User) -> list[dict[str, Any]]:
    """v1.8: empréstimos a amigos, cada um com o cronograma e o que foi recebido."""
    from app.models import LoanInstallment

    columns = [c.key for c in LoanInstallment.__table__.columns if c.key not in {"id", "loan_id"}]
    out = []
    for loan in _rows(db, PersonalLoan, user):
        items = db.scalars(
            select(LoanInstallment)
            .where(LoanInstallment.loan_id == uuid.UUID(loan["id"]))
            .order_by(LoanInstallment.number)
        )
        loan["installments"] = [{c: _serialize(getattr(i, c)) for c in columns} for i in items]
        out.append(loan)
    return out


def _ask(db: Session, user: User) -> list[dict[str, Any]]:
    from app.services import ask_history

    return ask_history.export(db, user)


def _support(db: Session, user: User) -> list[dict[str, Any]]:
    """Solicitações com as mensagens (as imagens ficam de fora: são baixadas pelo app)."""
    result = []
    for thread in db.scalars(select(SupportThread).where(SupportThread.user_id == user.id)):
        messages = db.scalars(
            select(SupportMessage)
            .where(SupportMessage.thread_id == thread.id)
            .order_by(SupportMessage.created_at)
        )
        result.append(
            {
                "title": thread.title,
                "kind": thread.kind,
                "status": thread.status,
                "created_at": thread.created_at.isoformat(),
                "messages": [
                    {
                        "from": "administração" if m.from_admin else "você",
                        "body": m.body,
                        "created_at": m.created_at.isoformat(),
                    }
                    for m in messages
                ],
            }
        )
    return result
