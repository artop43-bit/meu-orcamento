"""Normalização determinística PT-BR (moeda, data, número, telefone WhatsApp, e-mail, texto)."""

import math
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.core.errors import AppError
from app.core.money import MAX_MONEY, Q2

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+?55\s?)?(?:\(?\d{2}\)?\s?)?(?:9\d{4}|\d{4})[-\s]?\d{4}")
CURRENCY_RE = re.compile(
    r"(?:R\$\s*[-+]?|[-+]?\s*R\$\s*)(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2}|\d+\.\d{2})"
)
DATE_BR_RE = re.compile(r"\b(\d{2})[/-](\d{2})[/-](\d{2,4})\b")
DATE_ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")

# Números de planilhas/PDF/API: acima disso não é valor de verdade (e o float viraria infinito).
MAX_ABS_NUMBER = Decimal("1e15")
MAX_TEXT_CELL = 500


def slugify_column(raw: str, fallback: str = "coluna") -> str:
    text = unicodedata.normalize("NFKD", (raw or "").strip())
    ascii_text = "".join(ch for ch in text if not unicodedata.combining(ch))
    clean = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_text.lower()).strip("_")
    return clean[:48] or fallback


def normalize_phone(raw: str | None) -> tuple[str, str] | None:
    """Normaliza telefone para o padrão da Mensageria do Hub (@s.whatsapp.net ou @lid)."""
    from app.services.messaging import phones as messaging_phones

    value = (raw or "").strip()
    if not value:
        return None
    try:
        digits, jid = messaging_phones.normalize_phone(value)
    except AppError:
        return None
    if digits is None and jid.endswith("@lid"):
        return jid.split("@", 1)[0], jid
    return (digits or jid.split("@", 1)[0]), jid


def format_phone_display(phone: str | None) -> str:
    from app.services.messaging import phones as messaging_phones

    return messaging_phones.format_phone_display(phone)


def parse_number(raw: object) -> Decimal | None:
    """Aceita formatos BR ('R$ 1.234,56', '-45,90') e US ('1234.56', '1,234.56').

    Recusa (devolve None) NaN, infinito e números absurdos (acima de MAX_ABS_NUMBER).
    """
    value = _parse_decimal(raw)
    if value is None or not value.is_finite() or abs(value) >= MAX_ABS_NUMBER:
        return None
    return value


def parse_money(raw: object) -> Decimal | None:
    """Valor em reais de um negócio: 0 a MAX_MONEY, com 2 casas. None se inválido."""
    value = parse_number(raw)
    if value is None or value < 0:
        return None
    value = value.quantize(Q2)
    return value if value <= MAX_MONEY else None


def _parse_decimal(raw: object) -> Decimal | None:
    """Lê o número sem conferir a faixa (pode devolver NaN, infinito ou valor gigante)."""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, Decimal)):
        return Decimal(raw)
    if isinstance(raw, float):
        return Decimal(str(raw))
    text = str(raw).strip()
    if not text:
        return None
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1].strip()
    text = re.sub(r"(?i)r\$|\s|%|\u00a0", "", text)
    if text.startswith("-"):
        negative = True
        text = text[1:]
    elif text.startswith("+"):
        text = text[1:]
    if not text:
        return None
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        if re.fullmatch(r"\d+(?:,\d{1,4})", text):
            text = text.replace(",", ".")
        elif re.fullmatch(r"\d{1,3}(?:,\d{3})+", text):
            text = text.replace(",", "")
        else:
            text = text.replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+", text):
        text = text.replace(".", "")

    try:
        value = Decimal(text)
        return -value if negative else value
    except InvalidOperation:  # inclui "-sNaN" (a negação também levanta)
        return None


def parse_date(raw: object) -> str | None:
    """Converte datas BR/ISO para 'AAAA-MM-DD'."""
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.date().isoformat()
    if isinstance(raw, date):
        return raw.isoformat()
    text = str(raw).strip()
    if not text:
        return None

    iso = re.match(r"^(\d{4})-(\d{2})-(\d{2})(?:[T\s].*)?$", text)
    if iso:
        try:
            return date(int(iso[1]), int(iso[2]), int(iso[3])).isoformat()
        except ValueError:
            return None

    br = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})(?:\s.*)?$", text)
    if br:
        day, month, year = int(br[1]), int(br[2]), int(br[3])
        if year < 100:
            year += 2000 if year < 70 else 1900
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return None
    return None


def looks_like_currency(raw: object) -> bool:
    if raw is None:
        return False
    text = str(raw).strip()
    if not text:
        return False
    if re.search(r"(?i)r\$|\$|€", text):
        return parse_number(text) is not None
    return bool(re.fullmatch(r"[-+]?\d{1,3}(?:\.\d{3})*,\d{2}", text))


def infer_column_type(column_name: str, values: list[object]) -> str:
    """Infere o tipo de coluna: currency | date | number | phone | email | boolean | text."""
    non_empty = [v for v in values if v is not None and str(v).strip() != ""]
    if not non_empty:
        return "text"
    sample = non_empty[:80]
    total = len(sample)
    name_low = slugify_column(column_name, "")

    bool_hits = sum(
        1
        for v in sample
        if isinstance(v, bool)
        or str(v).strip().lower() in {"true", "false", "sim", "nao", "não", "s", "n"}
    )
    if bool_hits / total >= 0.85:
        return "boolean"

    email_hits = sum(1 for v in sample if EMAIL_RE.fullmatch(str(v).strip()))
    if email_hits / total >= 0.7:
        return "email"

    date_hits = sum(1 for v in sample if parse_date(v) is not None)
    if date_hits / total >= 0.75:
        return "date"

    currency_hits = sum(1 for v in sample if looks_like_currency(v))
    number_hits = sum(1 for v in sample if parse_number(v) is not None)

    if any(k in name_low for k in ("telefone", "celular", "whatsapp", "fone", "phone")):
        phone_hits = sum(1 for v in sample if normalize_phone(str(v)) is not None)
        if phone_hits / total >= 0.6:
            return "phone"

    if currency_hits / total >= 0.6 or (
        number_hits / total >= 0.8
        and any(
            k in name_low
            for k in (
                "valor",
                "preco",
                "total",
                "receita",
                "despesa",
                "saldo",
                "custo",
                "faturamento",
                "amount",
                "price",
                "revenue",
            )
        )
    ):
        return "currency"

    if number_hits / total >= 0.8:
        return "number"

    phone_hits = sum(
        1
        for v in sample
        if len(re.sub(r"\D", "", str(v))) in (10, 11, 12, 13) and PHONE_RE.search(str(v))
    )
    if phone_hits / total >= 0.75:
        return "phone"

    return "text"


def coerce_cell(value: object, col_type: str) -> object:
    if value is None:
        return None
    # NaN/infinito (ex.: JSON de API) não têm como ir para a tela: a célula fica vazia.
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
    if col_type == "date":
        return parse_date(value) or str(value)[:MAX_TEXT_CELL]
    if col_type in ("currency", "number"):
        num = parse_number(value)
        if num is not None:
            return float(num)
        # Parece número mas é inválido ("NaN", "Infinity", "1e400"): célula vazia.
        return None if _parse_decimal(value) is not None else str(value)[:MAX_TEXT_CELL]
    if col_type == "boolean":
        if isinstance(value, bool):
            return value
        low = str(value).strip().lower()
        if low in {"true", "sim", "s", "1"}:
            return True
        if low in {"false", "nao", "não", "n", "0"}:
            return False
        return str(value)[:MAX_TEXT_CELL]
    if col_type == "phone":
        norm = normalize_phone(str(value))
        return format_phone_display(norm[0]) if norm else str(value)[:MAX_TEXT_CELL]
    return str(value)[:MAX_TEXT_CELL]
