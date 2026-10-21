"""Vencimentos na agenda do celular (v1.4): calendário iCal por um link secreto.

O Google Agenda e o iPhone assinam o link e buscam de novo de tempos em tempos. Entram as contas
a pagar (vencimento), as faturas do cartão e as despesas previstas, do mês passado até 12 meses
à frente. O link leva um código aleatório longo; trocar o link desliga o anterior na hora.
Quem pediu "ocultar valores nos avisos" recebe os eventos sem os valores.
"""

import secrets
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.months import add_months, month_of, today_local
from app.models import User
from app.services import planned
from app.services.notify import brl

KINDS = {"expense", "installment", "recurring", "planned", "invoice"}
CRLF = "\r\n"


def new_token(db: Session, user: User) -> str:
    user.calendar_token = secrets.token_urlsafe(32)
    db.commit()
    return user.calendar_token


def revoke(db: Session, user: User) -> None:
    user.calendar_token = None
    db.commit()


def owner(db: Session, token: str) -> User:
    user = db.scalar(select(User).where(User.calendar_token == token)) if len(token) >= 32 else None
    if user is None:
        raise AppError(404, "not_found", "Calendário não encontrado.")
    return user


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    # Linhas de no máximo 75 caracteres (RFC 5545), continuação começando com espaço.
    out, rest = [], line
    while len(rest.encode()) > 75:
        cut = 74
        while len(rest[:cut].encode()) > 74:
            cut -= 1
        out.append(rest[:cut])
        rest = " " + rest[cut:]
    out.append(rest)
    return CRLF.join(out)


def build(db: Session, user: User, today: date | None = None) -> str:
    today = today or today_local()
    first = add_months(month_of(today, user.month_start_day), -1)
    events: list[dict[str, Any]] = []
    for offset in range(14):
        events.extend(planned.month_calendar(db, user, add_months(first, offset)))
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Meu Orcamento//Vencimentos//PT-BR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Meu Orçamento: vencimentos",
        "X-PUBLISHED-TTL:PT6H",
    ]
    seen: set[str] = set()
    for e in events:
        if e["kind"] not in KINDS or not e.get("date"):
            continue
        uid = f"{e['kind']}-{e.get('id')}-{e['date']}@meuorcamento"
        if uid in seen:
            continue
        seen.add(uid)
        day: date = e["date"]
        status = " (paga)" if e.get("paid") else ""
        value = "" if user.notify_hide_values else f" · {brl(e['amount'])}"
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{day:%Y%m%d}",
            f"DTEND;VALUE=DATE:{day + timedelta(days=1):%Y%m%d}",
            _fold(f"SUMMARY:{_escape(e['description'] + value + status)}"),
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return CRLF.join(lines) + CRLF
