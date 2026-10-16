"""Conversão tolerante de textos digitados ou exportados por bancos e pelo app antigo."""

import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation

_THOUSANDS_DOT = re.compile(r"^\d{1,3}(\.\d{3})+$")


def normalize_text(value: str) -> str:
    """Minúsculas, sem acentos e com espaços simples (para comparar nomes)."""
    text = unicodedata.normalize("NFKD", value)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text).strip().lower()


def parse_amount(value: object) -> Decimal | None:
    """Aceita 1234.56, "1.234,56", "R$ -12,30", "(12,30)", "1,234.56" etc."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float | Decimal):
        try:
            return Decimal(str(value)).quantize(Decimal("0.01"))
        except InvalidOperation:
            return None

    text = str(value).strip().replace("R$", "").replace("\xa0", "").replace(" ", "")
    if not text:
        return None
    negative = (
        text.startswith("-") or text.endswith("-") or (text.startswith("(") and text.endswith(")"))
    )
    text = text.strip("-+()")

    if "," in text and "." in text:
        # O separador que aparece por último é o decimal.
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".") if text.count(",") == 1 else text.replace(",", "")
    elif _THOUSANDS_DOT.match(text):
        text = text.replace(".", "")

    try:
        amount = Decimal(text).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None
    return -amount if negative else amount


_DATE_PATTERNS = [
    (re.compile(r"^(\d{4})-(\d{2})-(\d{2})"), ("y", "m", "d")),
    (re.compile(r"^(\d{2})/(\d{2})/(\d{4})$"), ("d", "m", "y")),
    (re.compile(r"^(\d{2})-(\d{2})-(\d{4})$"), ("d", "m", "y")),
    (re.compile(r"^(\d{2})/(\d{2})/(\d{2})$"), ("d", "m", "y2")),
    (re.compile(r"^(\d{4})(\d{2})(\d{2})"), ("y", "m", "d")),  # OFX: 20261005120000[-3:BRT]
]


def parse_date(value: object) -> date | None:
    text = str(value or "").strip()
    for pattern, order in _DATE_PATTERNS:
        match = pattern.match(text)
        if not match:
            continue
        parts = dict(zip(order, match.groups(), strict=True))
        year = int(parts["y"]) if "y" in parts else 2000 + int(parts["y2"])
        try:
            return date(year, int(parts["m"]), int(parts["d"]))
        except ValueError:
            return None
    return None
