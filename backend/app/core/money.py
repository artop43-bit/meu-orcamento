"""Constantes e formatação única de valores monetários e quantidades no Hub."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from app.core.errors import AppError

ZERO = Decimal("0.00")
Q2 = Decimal("0.01")
Q3 = Decimal("0.001")
MAX_MONEY = Decimal("9999999999.99")
MONEY_RANGE_MESSAGE = "Informe um valor entre R$ 0,00 e R$ 9.999.999.999,99."
MAX_QTY = Decimal("999999999.999")
QTY_RANGE_MESSAGE = "Informe uma quantidade entre 0 e 999.999.999,999."


def fmt_num(value: Decimal | float | int | None) -> str:
    """Formata um número em pt-BR sem prefixo R$ (ex.: '1.234,56')."""
    dec = Decimal(str(value or ZERO)).quantize(Q2, rounding=ROUND_HALF_UP)
    return f"{dec:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def brl(
    value: Decimal | float | int | None,
    *,
    abs_val: bool = False,
    signed: bool = False,
) -> str:
    """Formata valores em reais no padrão brasileiro ('R$ 1.234,56')."""
    amount = Decimal(str(value if value is not None else ZERO)).quantize(Q2, rounding=ROUND_HALF_UP)
    text = f"{abs(amount):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    if abs_val:
        return f"R$ {text}"
    sign = "-" if amount < ZERO else ("+" if signed and amount > ZERO else "")
    return f"{sign}R$ {text}"


def to_dec(
    value: Any,
    *,
    field: str = "valor",
    allow_negative: bool = False,
    scale: Decimal = Q2,
) -> Decimal:
    """Converte entrada numérica/texto em Decimal validando limites sem nunca lançar erro 500."""
    if value is None or value == "":
        return ZERO.quantize(scale)
    try:
        dec = Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, ValueError) as exc:
        raise AppError(422, "invalid_number", f"Valor inválido para {field}.") from exc
    if not dec.is_finite():
        raise AppError(422, "invalid_number", f"Valor inválido para {field}.")
    if not allow_negative and dec < ZERO:
        raise AppError(422, "invalid_number", f"O campo {field} não pode ser negativo.")
    limit = MAX_QTY if scale == Q3 else MAX_MONEY
    range_msg = QTY_RANGE_MESSAGE if scale == Q3 else MONEY_RANGE_MESSAGE
    if dec.copy_abs() > limit:
        raise AppError(422, "amount_out_of_range", f"{range_msg} ({field}).")
    return dec.quantize(scale, rounding=ROUND_HALF_UP)
