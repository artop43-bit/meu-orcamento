"""Exportação: lançamentos em CSV ou Excel e backup completo em JSON."""

import csv
import io
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.months import format_month
from app.models import Category, Expense, Goal, Income, Investment, RecurringItem, User
from app.services import budget

COLUMNS = ["Mês", "Tipo", "Data", "Descrição", "Categoria", "Valor", "Pago", "Parcela", "Fixa"]


def transactions(db: Session, user: User, start: date, end: date) -> list[dict[str, Any]]:
    categories = {c.id: c.name for c in budget.list_categories(db, user)}
    rows: list[dict[str, Any]] = []
    for income in db.scalars(
        select(Income)
        .where(Income.user_id == user.id, Income.month.between(start, end))
        .order_by(Income.month, Income.created_at)
    ):
        rows.append(
            {
                "month": income.month,
                "type": "Renda",
                "date": None,
                "description": income.description,
                "category": "",
                "amount": income.amount,
                "paid": None,
                "installment": "",
                "recurring": income.recurring_id is not None,
            }
        )
    for expense in db.scalars(
        select(Expense)
        .where(Expense.user_id == user.id, Expense.month.between(start, end))
        .order_by(Expense.month, Expense.due_date, Expense.created_at)
    ):
        rows.append(
            {
                "month": expense.month,
                "type": "Conta",
                "date": expense.due_date,
                "description": expense.description,
                "category": categories.get(expense.category_id, "") if expense.category_id else "",
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
    rows.sort(key=lambda r: (r["month"], r["type"] != "Renda", r["date"] or date.max))
    return rows


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
                float(r["amount"]),
                _yes_no(r["paid"]),
                r["installment"],
                _yes_no(r["recurring"]),
            ]
        )
    for row in sheet.iter_rows(min_row=2):
        row[2].number_format = "DD/MM/YYYY"
        row[5].number_format = money_format
    sheet.auto_filter.ref = sheet.dimensions
    for index, width in enumerate([10, 8, 12, 40, 18, 15, 7, 9, 7], start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width

    resume = workbook.create_sheet("Resumo")
    header(resume, ["Mês", "Renda", "Contas", "Pago", "Saldo", "% comprometido"])
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

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


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
        "categories": _rows(db, Category, user),
        "recurring": _rows(db, RecurringItem, user),
        "incomes": _rows(db, Income, user),
        "expenses": _rows(db, Expense, user),
        "goals": _rows(db, Goal, user),
        "investments": _rows(db, Investment, user),
    }
