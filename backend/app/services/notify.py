"""Avisos por e-mail: vencimentos, novo acesso e resumo do mês.

- Um e-mail de vencimentos por dia, no máximo (8h, horário de Brasília), com tudo junto.
- O mesmo aviso nunca sai duas vezes (tabela notification_log, com chave única).
- Todo e-mail de aviso tem o link "Não quero mais receber" (descadastro com um clique, sem
  login: o link leva um token assinado com a SECRET_KEY).
- Só recebe quem confirmou o e-mail e tem acesso liberado.
"""

import base64
import hashlib
import hmac
import html
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.email import send_email
from app.core.months import add_months
from app.db.types import utcnow
from app.models import (
    EmailLog,
    Expense,
    Goal,
    KnownDevice,
    NotificationLog,
    PlannedExpense,
    User,
)

logger = logging.getLogger(__name__)

MONTHS = [
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
]
KINDS = {"due": "lembretes de vencimento", "monthly": "resumo do mês"}
SEND_HOUR = 8


def local_now() -> datetime:
    return datetime.now(ZoneInfo(get_settings().timezone))


def brl(value: Decimal | float | int) -> str:
    text = f"{Decimal(value):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {text}"


def short_date(day: date) -> str:
    return day.strftime("%d/%m")


def _link(path: str) -> str:
    return get_settings().frontend_url.rstrip("/") + path


# ---------------------------------------------------------------- descadastro


def _signature(user_id: uuid.UUID, kind: str) -> str:
    key = get_settings().secret_key.encode()
    digest = hmac.new(key, f"unsubscribe:{user_id}:{kind}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest[:18]).decode().rstrip("=")


def unsubscribe_token(user_id: uuid.UUID, kind: str) -> str:
    return f"{user_id.hex}.{kind}.{_signature(user_id, kind)}"


def unsubscribe(db: Session, token: str) -> tuple[User, str] | None:
    """Desliga o aviso indicado no token. Devolve (usuário, tipo) ou None se o token for inválido."""
    try:
        raw_id, kind, sig = token.split(".", 2)
        user_id = uuid.UUID(hex=raw_id)
    except ValueError:
        return None
    if kind not in KINDS or not hmac.compare_digest(sig, _signature(user_id, kind)):
        return None
    user = db.get(User, user_id)
    if user is None:
        return None
    if kind == "due":
        user.notify_due = False
    else:
        user.notify_monthly = False
    db.commit()
    return user, kind


# ---------------------------------------------------------------- montagem do e-mail


@dataclass
class Section:
    title: str
    rows: list[tuple[str, str, str]] = field(default_factory=list)  # (descrição, data, valor)
    note: str | None = None


@dataclass
class Message:
    subject: str
    heading: str
    intro: str
    sections: list[Section]
    button: tuple[str, str] | None  # (texto, link)
    unsubscribe_kind: str | None = None
    outro: str | None = None


def render(message: Message, user: User) -> tuple[str, str, dict[str, str]]:
    """Texto puro + HTML (com estilos embutidos, como os clientes de e-mail exigem)."""
    headers: dict[str, str] = {}
    unsubscribe_url = None
    if message.unsubscribe_kind:
        token = unsubscribe_token(user.id, message.unsubscribe_kind)
        unsubscribe_url = _link(f"/descadastrar?t={token}")
        api_url = _link(f"/api/notifications/unsubscribe?t={token}")
        headers["List-Unsubscribe"] = f"<{api_url}>"
        headers["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"

    lines = [message.heading, "", message.intro, ""]
    for section in message.sections:
        lines.append(section.title.upper())
        for desc, when, value in section.rows:
            lines.append(
                f"- {desc}" + (f" · {when}" if when else "") + (f" · {value}" if value else "")
            )
        if section.note:
            lines.append(section.note)
        lines.append("")
    if message.button:
        lines += [f"{message.button[0]}: {message.button[1]}", ""]
    if message.outro:
        lines += [message.outro, ""]
    if unsubscribe_url:
        lines.append(
            f"Para não receber mais {KINDS[message.unsubscribe_kind]}: {unsubscribe_url}"  # type: ignore[index]
        )
    lines.append("Meu Orçamento")
    text = "\n".join(lines)

    e = html.escape
    accent = "#1f7a62"
    parts = [
        '<!doctype html><html lang="pt-BR"><body style="margin:0;padding:0;background:#f3f4f2;">',
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f2;padding:24px 12px;">',
        '<tr><td align="center"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="max-width:560px;background:#ffffff;border-radius:12px;font-family:Segoe UI,Arial,sans-serif;color:#17201c;">',
        f'<tr><td style="padding:20px 24px;border-bottom:3px solid {accent};font-weight:700;font-size:16px;color:{accent};">Meu Orçamento</td></tr>',
        f'<tr><td style="padding:24px 24px 8px;"><h1 style="margin:0 0 8px;font-size:20px;">{e(message.heading)}</h1>'
        f'<p style="margin:0;font-size:15px;line-height:1.5;color:#4a5550;">{e(message.intro)}</p></td></tr>',
    ]
    for section in message.sections:
        parts.append(
            f'<tr><td style="padding:16px 24px 0;"><p style="margin:0 0 8px;font-size:12px;font-weight:700;'
            f'letter-spacing:.06em;text-transform:uppercase;color:#6b7570;">{e(section.title)}</p>'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="font-size:14px;">'
        )
        for desc, when, value in section.rows:
            parts.append(
                '<tr><td style="padding:8px 0;border-bottom:1px solid #e6e9e6;">'
                f"{e(desc)}"
                + (
                    f'<br><span style="color:#6b7570;font-size:12px;">{e(when)}</span>'
                    if when
                    else ""
                )
                + "</td>"
                f'<td align="right" style="padding:8px 0;border-bottom:1px solid #e6e9e6;font-weight:600;white-space:nowrap;">{e(value)}</td></tr>'
            )
        parts.append("</table>")
        if section.note:
            parts.append(
                f'<p style="margin:8px 0 0;font-size:13px;color:#4a5550;">{e(section.note)}</p>'
            )
        parts.append("</td></tr>")
    if message.button:
        label, url = message.button
        parts.append(
            f'<tr><td style="padding:24px;"><a href="{e(url)}" style="display:inline-block;background:{accent};'
            'color:#ffffff;text-decoration:none;font-weight:600;padding:12px 20px;border-radius:8px;">'
            f"{e(label)}</a></td></tr>"
        )
    if message.outro:
        parts.append(
            f'<tr><td style="padding:0 24px 16px;font-size:13px;color:#4a5550;">{e(message.outro)}</td></tr>'
        )
    footer = "Você recebe este e-mail porque tem uma conta no Meu Orçamento."
    if unsubscribe_url:
        footer += (
            f' <a href="{e(unsubscribe_url)}" style="color:#6b7570;">Não quero mais receber '
            f"{e(KINDS[message.unsubscribe_kind])}</a>."  # type: ignore[index]
        )
    parts.append(
        f'<tr><td style="padding:16px 24px 24px;font-size:12px;color:#6b7570;border-top:1px solid #e6e9e6;">{footer}</td></tr>'
    )
    parts.append("</table></td></tr></table></body></html>")
    return text, "".join(parts), headers


def deliver(db: Session, user: User, message: Message) -> None:
    """Registra no painel (E-mails enviados) e envia. Falha de envio fica no log do servidor."""
    text, body_html, headers = render(message, user)
    db.add(EmailLog(to=user.email, subject=message.subject[:200], body=text))
    db.commit()
    try:
        send_email(user.email, message.subject, text, html=body_html, headers=headers)
    except Exception as exc:  # SMTP fora do ar: o próximo ciclo não reenvia (já registrado)
        logger.warning("Aviso por e-mail não enviado para %s: %s", user.id, exc)


def _claim(db: Session, user: User, kind: str, ref: str) -> bool:
    """Marca o aviso como enviado ANTES de enviar; se já existia, não envia de novo."""
    db.add(NotificationLog(user_id=user.id, kind=kind, ref=ref))
    try:
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False


def _eligible(user: User) -> bool:
    return user.email_verified and user.access_status == "approved"


# ---------------------------------------------------------------- vencimentos


def _value(user: User, amount: Decimal) -> str:
    return "" if user.notify_hide_values else brl(amount)


def due_message(db: Session, user: User, today: date) -> Message | None:
    from app.services import cards

    ahead = today + timedelta(days=user.notify_due_days)
    yesterday = today - timedelta(days=1)
    expenses = list(
        db.scalars(
            select(Expense)
            .where(
                Expense.user_id == user.id,
                Expense.paid.is_(False),
                Expense.card_id.is_(None),  # compras no cartão entram pela fatura
                Expense.due_date.in_([ahead, today, yesterday]),
            )
            .order_by(Expense.due_date, Expense.description)
        )
    )
    planned = list(
        db.scalars(
            select(PlannedExpense).where(
                PlannedExpense.user_id == user.id,
                PlannedExpense.expense_id.is_(None),
                PlannedExpense.date.in_([ahead, today]),
            )
        )
    )
    invoices = []
    for card in cards.credit_cards(db, user):
        for day in {ahead, today}:
            data = cards.invoice(db, card, day.replace(day=1), today)
            if data["due_date"] == day and data["count"] and data["status"] != "paid":
                invoices.append((card, data))

    sections: list[Section] = []

    def rows_for(day: date) -> list[tuple[str, str, str]]:
        rows = [
            (e.description, f"vence {short_date(day)}", _value(user, e.amount))
            for e in expenses
            if e.due_date == day
        ]
        rows += [
            (
                f"Fatura {c.name}",
                f"vence {short_date(day)}",
                _value(user, d["total"] - d["paid_total"]),
            )
            for c, d in invoices
            if d["due_date"] == day
        ]
        rows += [
            (f"{p.description} (prevista)", short_date(day), _value(user, p.amount))
            for p in planned
            if p.date == day
        ]
        return rows

    late = rows_for(yesterday)
    if late:
        sections.append(Section("Venceu ontem e está em aberto", late))
    now_rows = rows_for(today)
    if now_rows:
        sections.append(Section("Vence hoje", now_rows))
    soon = rows_for(ahead) if ahead != today else []
    if soon:
        days = user.notify_due_days
        sections.append(Section(f"Vence em {days} dia{'s' if days > 1 else ''}", soon))
    if not sections:
        return None

    count = sum(len(s.rows) for s in sections)
    subject = (
        f"{count} conta(s) a pagar · {short_date(today)}"
        if not late
        else f"Conta em atraso e vencimentos · {short_date(today)}"
    )
    return Message(
        subject=f"Meu Orçamento: {subject}",
        heading="Vencimentos próximos",
        intro="Contas ainda não marcadas como pagas. Se já pagou, marque como paga no app para não receber novo aviso.",
        sections=sections,
        button=("Abrir no app", _link(f"/orcamento/{today:%Y-%m}")),
        unsubscribe_kind="due",
        outro="Você pode mudar a antecedência ou ocultar os valores em Ajustes › Preferências.",
    )


# ---------------------------------------------------------------- resumo do mês


def monthly_message(db: Session, user: User, month: date) -> Message | None:
    from app.services import budget

    summary = budget.get_month(db, user, month).summary
    income, expenses = summary["income_total"], summary["expense_total"]
    if income <= 0 and expenses <= 0:
        return None
    balance = income - expenses
    rate = f"{float(balance / income * 100):.1f}%".replace(".", ",") if income > 0 else "—"
    hide = user.notify_hide_values
    result_rows = [
        ("Receitas", "", "" if hide else brl(income)),
        ("Despesas", "", "" if hide else brl(expenses)),
        ("Resultado", "positivo" if balance >= 0 else "negativo", "" if hide else brl(balance)),
        ("Taxa de poupança", "", rate),
    ]
    top = sorted(summary["by_category"], key=lambda c: c["total"], reverse=True)[:3]
    category_rows = [
        (
            c["name"],
            f"{float(c['total'] / expenses * 100):.0f}% das despesas" if expenses > 0 else "",
            "" if hide else brl(c["total"]),
        )
        for c in top
    ]
    goals = list(
        db.scalars(
            select(Goal).where(Goal.user_id == user.id, Goal.completed_at.is_(None)).limit(5)
        )
    )
    goal_rows = [
        (
            g.name,
            f"{float(g.current_amount / g.target_amount * 100):.0f}% concluída"
            if g.target_amount > 0
            else "",
            "" if hide else f"{brl(g.current_amount)} de {brl(g.target_amount)}",
        )
        for g in goals
    ]
    sections = [Section("Resultado", result_rows)]
    if category_rows:
        sections.append(Section("Maiores categorias", category_rows))
    if goal_rows:
        sections.append(Section("Metas", goal_rows))
    name = f"{MONTHS[month.month - 1]} de {month.year}"
    return Message(
        subject=f"Meu Orçamento: resumo de {name}",
        heading=f"Resumo de {name}",
        intro=(
            "O mês fechou com resultado positivo."
            if balance >= 0
            else "O mês fechou com despesas acima das receitas."
        ),
        sections=sections,
        button=("Ver Insights do mês", _link(f"/analises?mes={month:%Y-%m}")),
        unsubscribe_kind="monthly",
    )


# ---------------------------------------------------------------- execução diária


def run_daily(db: Session, now: datetime | None = None) -> dict[str, int]:
    """Envia os avisos do dia (chamado pelo agendador; pode rodar várias vezes: não duplica)."""
    now = now or local_now()
    if now.hour < SEND_HOUR:
        return {"due": 0, "monthly": 0}
    today = now.date()
    previous = add_months(today.replace(day=1), -1)
    sent = {"due": 0, "monthly": 0}
    users = list(db.scalars(select(User)))
    for user in users:
        if not _eligible(user):
            continue
        try:
            if user.notify_due:
                message = due_message(db, user, today)
                if message and _claim(db, user, "due", today.isoformat()):
                    deliver(db, user, message)
                    sent["due"] += 1
            if user.notify_monthly and today.day == 1:
                message = monthly_message(db, user, previous)
                if message and _claim(db, user, "monthly", f"{previous:%Y-%m}"):
                    deliver(db, user, message)
                    sent["monthly"] += 1
        except Exception as exc:  # um usuário com problema não impede os outros
            db.rollback()
            logger.exception("Avisos do dia falharam para %s: %s", user.id, exc)
    return sent


# ---------------------------------------------------------------- novo acesso


BROWSERS = (
    ("Edg", "Edge"),
    ("OPR", "Opera"),
    ("Firefox", "Firefox"),
    ("Chrome", "Chrome"),
    ("Safari", "Safari"),
)
SYSTEMS = (
    ("iPhone", "iPhone"),
    ("iPad", "iPad"),
    ("Android", "Android"),
    ("Windows", "Windows"),
    ("Mac OS X", "macOS"),
    ("Macintosh", "macOS"),
    ("CrOS", "ChromeOS"),
    ("Linux", "Linux"),
)


def device_label(user_agent: str | None) -> str:
    ua = user_agent or ""
    browser = next((name for token, name in BROWSERS if token in ua), "Navegador")
    system = next((name for token, name in SYSTEMS if token in ua), "sistema desconhecido")
    return f"{browser} no {system}" if system != "sistema desconhecido" else browser


def _fingerprint(label: str) -> str:
    return hashlib.sha256(re.sub(r"\s+", " ", label.lower()).encode()).hexdigest()


def register_login(
    db: Session, user: User, user_agent: str | None, ip: str | None
) -> Message | None:
    """Guarda o aparelho. Se for novo (e a conta já tiver outro), devolve o aviso a enviar."""
    label = device_label(user_agent)
    fingerprint = _fingerprint(label)
    known = list(db.scalars(select(KnownDevice).where(KnownDevice.user_id == user.id)))
    match = next((d for d in known if d.fingerprint == fingerprint), None)
    now = utcnow()
    if match:
        match.last_seen_at = now
        return None
    db.add(KnownDevice(user_id=user.id, fingerprint=fingerprint, label=label[:80]))
    if not known:  # primeiro aparelho da conta: nada a avisar
        return None
    when = local_now().strftime("%d/%m/%Y às %H:%M")
    return Message(
        subject="Meu Orçamento: novo acesso à sua conta",
        heading="Novo acesso à sua conta",
        intro="Sua conta foi acessada por um aparelho ou navegador que ainda não tinha sido usado.",
        sections=[
            Section(
                "Detalhes",
                [("Quando", "", when), ("Aparelho", "", label)]
                + ([("Endereço IP", "", ip)] if ip else []),
                note="Se foi você, não é preciso fazer nada.",
            )
        ],
        button=None,  # o link "Não fui eu" é incluído por quem chama (token de uso único)
    )
