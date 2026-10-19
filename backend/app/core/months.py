"""Meses do orçamento: representados como a data do dia 1 (ex.: 2026-10-01)."""

import calendar
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.core.config import get_settings
from app.core.errors import AppError

MONTH_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
# Datas aceitas no app: nada de "08/08/888888".
MIN_YEAR = 2000
MAX_YEAR = 2100
DATE_RANGE_MESSAGE = f"Data inválida: use um ano entre {MIN_YEAR} e {MAX_YEAR}."


def check_date(value: date) -> date:
    """Validação usada nos schemas: recusa anos fora do intervalo realista."""
    if not MIN_YEAR <= value.year <= MAX_YEAR:
        raise ValueError(DATE_RANGE_MESSAGE)
    return value


def parse_month(value: str) -> date:
    match = MONTH_RE.match(value)
    if not match:
        raise AppError(400, "invalid_month", "Mês inválido. Use o formato AAAA-MM.")
    if not MIN_YEAR <= int(match[1]) <= MAX_YEAR:
        raise AppError(400, "invalid_month", DATE_RANGE_MESSAGE)
    return date(int(match[1]), int(match[2]), 1)


def format_month(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def add_months(value: date, count: int) -> date:
    index = value.year * 12 + value.month - 1 + count
    return date(index // 12, index % 12 + 1, 1)


def with_day(month: date, day: int) -> date:
    """O dia no mês, ajustado ao último dia (ex.: dia 31 em fevereiro vira 28/29)."""
    last = calendar.monthrange(month.year, month.month)[1]
    return date(month.year, month.month, min(day, last))


def current_month() -> date:
    today = datetime.now(ZoneInfo(get_settings().timezone)).date()
    return today.replace(day=1)
