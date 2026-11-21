"""Números e identificadores (JID) do WhatsApp: normalização e exibição.

- Número: `<dígitos>@s.whatsapp.net` (o formato antigo `@c.us` é aceito na entrada).
- LID: `<dígitos>@lid`, usado quando o WhatsApp esconde o número do contato.
"""

import re

from app.core.errors import AppError

PN_SUFFIX = "@s.whatsapp.net"
LID_SUFFIX = "@lid"
DEFAULT_CONTACT_NAME = "Contato do WhatsApp"

_PN_SERVERS = {"s.whatsapp.net", "c.us"}
_INVALID_PHONE = "Informe um número de WhatsApp válido (com DDD)."
# Nomes mascarados do WhatsApp (ex.: "+55·······80") ou pontuação solta.
_MASKED_PHONE_RE = re.compile(r"^\+?\d{0,4}[\s\-]?[·•*∙\.]{3,}\d{0,4}$")
_ONLY_PUNCT_RE = re.compile(r"^[\W_]+$")


def is_placeholder_name(value: str | None) -> bool:
    """Nome que não identifica o contato (vazio, genérico, só pontuação ou mascarado)."""
    text = " ".join((value or "").split()).strip()
    if not text or text == DEFAULT_CONTACT_NAME:
        return True
    if _MASKED_PHONE_RE.match(text):
        return True
    return bool(_ONLY_PUNCT_RE.match(text))


def digits_only(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def parse_jid(raw: str | None) -> tuple[str, str] | None:
    """Classifica um JID: ("pn", "<dígitos>@s.whatsapp.net") ou ("lid", "<dígitos>@lid").

    Tira o sufixo de aparelho (":12") e ignora o que não é conversa individual (grupos,
    status, canais), devolvendo None.
    """
    value = (raw or "").strip().lower()
    if "@" not in value:
        return None
    user, server = value.rsplit("@", 1)
    user = user.split(":", 1)[0]
    if not user.isdigit():
        return None
    if server in _PN_SERVERS and 8 <= len(user) <= 15:
        return "pn", f"{user}{PN_SUFFIX}"
    if server == "lid" and 6 <= len(user) <= 24:
        return "lid", f"{user}{LID_SUFFIX}"
    return None


def split_jids(*jids: str | None) -> tuple[str | None, str | None]:
    """Dos JIDs recebidos, separa o do número (pn) e o LID. Cada um pode faltar."""
    pn: str | None = None
    lid: str | None = None
    for raw in jids:
        parsed = parse_jid(raw)
        if parsed is None:
            continue
        kind, jid = parsed
        if kind == "pn" and pn is None:
            pn = jid
        elif kind == "lid" and lid is None:
            lid = jid
    return pn, lid


def phone_from_jid(raw: str | None) -> str | None:
    """Dígitos do número de um JID de número (com ou sem aparelho); None para LID e outros."""
    parsed = parse_jid(raw)
    if parsed is None or parsed[0] != "pn":
        return None
    return parsed[1].split("@", 1)[0]


def normalize_phone(raw: str) -> tuple[str | None, str]:
    """Normaliza o número (ou JID) digitado pela pessoa.

    Retorna (dígitos do número, remote_jid). Para um LID, os dígitos vêm como None.
    Números brasileiros com 10 ou 11 dígitos sem o 55 ganham o 55.
    """
    value = (raw or "").strip().lower()
    if not value:
        raise AppError(400, "invalid_phone", _INVALID_PHONE)

    if value.endswith(LID_SUFFIX):
        parsed = parse_jid(value)
        if parsed is None:
            raise AppError(400, "invalid_phone", "Identificador de contato inválido.")
        return None, parsed[1]

    cleaned = re.sub(r"@(c\.us|s\.whatsapp\.net)$", "", value)
    digits = digits_only(cleaned)
    if len(digits) in (10, 11) and not digits.startswith("55"):
        digits = f"55{digits}"
    if len(digits) < 8 or len(digits) > 15:
        raise AppError(400, "invalid_phone", _INVALID_PHONE)
    return digits, f"{digits}{PN_SUFFIX}"


def format_phone_display(phone: str | None) -> str:
    """Formata um número brasileiro (55 + DDD + 8/9 dígitos); "" quando não há número."""
    digits = digits_only(phone)
    if digits.startswith("55") and len(digits) == 13:
        return f"+55 ({digits[2:4]}) {digits[4:9]}-{digits[9:]}"
    if digits.startswith("55") and len(digits) == 12:
        return f"+55 ({digits[2:4]}) {digits[4:8]}-{digits[8:]}"
    return f"+{digits}" if digits else ""
