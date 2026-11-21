"""Helpers de datas e meses financeiros alinhados ao núcleo do Meu Orçamento."""

from __future__ import annotations

from datetime import date

from app.core.months import (
    add_months,
    cycle_date,
    cycle_range,
    format_month,
    month_of,
    today_local,
    with_day,
)
from app.services.insights import MONTH_NAMES


def month_label(month: date, include_year: bool = True) -> str:
    name = MONTH_NAMES[month.month - 1]
    return f"{name} de {month.year}" if include_year else name


def short_date(day: date) -> str:
    return f"{day.day:02d}/{day.month:02d}/{day.year}"


__all__ = [
    "MONTH_NAMES",
    "add_months",
    "cycle_date",
    "cycle_range",
    "format_month",
    "month_label",
    "month_of",
    "short_date",
    "today_local",
    "with_day",
]
