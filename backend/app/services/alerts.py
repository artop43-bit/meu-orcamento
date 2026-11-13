"""v1.0: alertas inteligentes do mês.

- Gasto fora do padrão: despesa bem acima do normal da categoria (mais de 2,5× a mediana dos
  últimos 6 meses, e pelo menos R$ 100 acima dela).
- Estabelecimento novo com valor alto: descrição nunca vista nos últimos 12 meses, a partir de
  R$ 300.
- Assinatura mais cara: conta fixa ou cobrança que se repete com valor 5% (e R$ 2) acima do mês
  anterior.
- Renovação anual: conta fixa anual que vence nos próximos 7 dias.

Os alertas aparecem no Orçamento; a rotina diária leva os novos para a caixa de Mensagens e
manda um e-mail com tudo junto (desligável). Cada alerta sai uma vez só (notification_log).
"""

import logging
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from statistics import median
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.months import add_months, cycle_date, month_of
from app.models import Category, Expense, InboxItem, RecurringItem, User
from app.services import notify
from app.services.auth import Mailer
from app.services.suggest import normalize

logger = logging.getLogger(__name__)

UNUSUAL_FACTOR = Decimal("2.5")
UNUSUAL_MIN_DIFF = Decimal("100")
NEW_MERCHANT_MIN = Decimal("300")
PRICE_UP = Decimal("0.05")
PRICE_UP_MIN = Decimal("2")
RENEWAL_DAYS = 7


CODES = {"unusual": "u", "new_merchant": "n", "price_up": "p", "renewal": "r", "loan_late": "l"}


def _alert(kind: str, key: str, title: str, text: str, **extra: Any) -> dict[str, Any]:
    # Chave curta e estável (cabe nos 40 caracteres do registro de avisos enviados).
    return {"kind": kind, "key": f"{CODES[kind]}:{key}"[:40], "title": title, "text": text, **extra}


def month_alerts(
    db: Session, user: User, month: date, today: date | None = None
) -> list[dict[str, Any]]:
    today = today or date.today()
    brl = notify.brl
    alerts: list[dict[str, Any]] = []
    current = list(
        db.scalars(
            select(Expense).where(
                Expense.user_id == user.id,
                Expense.month == month,
                Expense.loan_id.is_(None),
                Expense.personal_loan_id.is_(None),
            )
        )
    )
    past = list(
        db.scalars(
            select(Expense).where(
                Expense.user_id == user.id,
                Expense.month >= add_months(month, -12),
                Expense.month < month,
            )
        )
    )
    names = {c.id: c.name for c in db.scalars(select(Category).where(Category.user_id == user.id))}

    by_category: dict[Any, list[Decimal]] = defaultdict(list)
    for e in past:
        if (
            e.month >= add_months(month, -6)
            and e.recurring_id is None
            and e.installment_group_id is None
        ):
            by_category[e.category_id].append(e.amount)
    seen = {normalize(e.description) for e in past}

    for e in current:
        if e.recurring_id or e.installment_group_id:
            continue
        values = by_category.get(e.category_id) or []
        if len(values) >= 3:
            typical = Decimal(median(values))
            if e.amount > typical * UNUSUAL_FACTOR and e.amount - typical >= UNUSUAL_MIN_DIFF:
                alerts.append(
                    _alert(
                        "unusual",
                        e.id.hex,
                        f"Gasto acima do padrão: {e.description}",
                        f"{brl(e.amount)} em {names.get(e.category_id, 'Sem categoria')}; o "
                        f"normal da categoria é cerca de {brl(typical)} por lançamento.",
                        expense_id=e.id,
                    )
                )
                continue
        key = normalize(e.description)
        if key and key not in seen and e.amount >= NEW_MERCHANT_MIN and past:
            alerts.append(
                _alert(
                    "new_merchant",
                    str(e.id),
                    f"Valor alto em um lugar novo: {e.description}",
                    f"{brl(e.amount)}, primeira vez nos últimos 12 meses. Confira se reconhece "
                    "a cobrança.",
                    expense_id=e.id,
                )
            )

    # Assinaturas e contas fixas: aumento de valor em relação ao mês anterior. Vale para contas
    # fixas e para cobranças que aparecem uma vez por mês nos 3 meses anteriores (assinaturas);
    # gastos que variam por natureza (mercado, combustível) ficam de fora.
    monthly: dict[str, dict[date, list[Decimal]]] = defaultdict(lambda: defaultdict(list))
    for e in past:
        if e.month >= add_months(month, -3):
            monthly[normalize(e.description)][e.month].append(e.amount)

    def subscription_like(key: str) -> bool:
        months = monthly.get(key, {})
        return len(months) == 3 and all(len(v) == 1 for v in months.values())

    for e in current:
        key = normalize(e.description)
        last = monthly.get(key, {}).get(add_months(month, -1))
        if not last or e.installment_group_id or not (e.recurring_id or subscription_like(key)):
            continue
        before = last[0]
        if e.amount > before * (1 + PRICE_UP) and e.amount - before >= PRICE_UP_MIN:
            pct = round(float((e.amount - before) / before * 100))
            alerts.append(
                _alert(
                    "price_up",
                    e.id.hex,
                    f"Ficou mais caro: {e.description}",
                    f"Passou de {brl(before)} para {brl(e.amount)} (+{pct}%) em relação ao mês "
                    "anterior.",
                    expense_id=e.id,
                )
            )

    # Renovação anual nos próximos dias.
    start_day = user.month_start_day
    for item in db.scalars(
        select(RecurringItem).where(
            RecurringItem.user_id == user.id,
            RecurringItem.kind == "expense",
            RecurringItem.interval_months == 12,
        )
    ):
        if not item.due_day:
            continue
        for candidate in (month, add_months(month, 1)):
            if (
                candidate.year * 12
                + candidate.month
                - item.start_month.year * 12
                - item.start_month.month
            ) % 12:
                continue
            due = cycle_date(candidate, item.due_day, start_day)
            if today <= due <= today + timedelta(days=RENEWAL_DAYS):
                alerts.append(
                    _alert(
                        "renewal",
                        f"{item.id.hex[:24]}:{due:%Y}",
                        f"Renovação anual: {item.description}",
                        f"{brl(item.amount)} vence em {due:%d/%m}. Se não usa mais, cancele "
                        "antes da renovação.",
                    )
                )
    alerts.extend(_loan_alerts(db, user, today))
    return alerts


def _loan_alerts(db: Session, user: User, today: date) -> list[dict[str, Any]]:
    """v1.8: parcela de empréstimo a amigo vencida e não paga (uma vez por parcela)."""
    from app.services import personal_loans

    out = []
    for loan in personal_loans.all_loans(db, user, today):
        if loan["settled_at"] or not loan["late_count"]:
            continue
        late = [i for i in loan["installments"] if i["status"] == "late"]
        first = late[0]
        count = len(late)
        what = "parcela atrasada" if count == 1 else f"{count} parcelas atrasadas"
        if loan["direction"] == "owes_me":
            title = f"{loan['person']} está com {what}"
            text = (
                f"{notify.brl(loan['late_amount'])} em aberto, desde {first['due_date']:%d/%m}. "
                "Na tela Divisões dá para mandar a cobrança por Pix."
            )
        else:
            title = f"Você está com {what} com {loan['person']}"
            text = (
                f"{notify.brl(loan['late_amount'])} em aberto, desde {first['due_date']:%d/%m}. "
                "Quando pagar, marque na tela Divisões."
            )
        out.append(_alert("loan_late", f"{loan['id'].hex[:24]}:{first['number']}", title, text))
    return out


def run_daily(db: Session, mail: Mailer, today: date | None = None) -> int:
    """Leva os alertas novos para a caixa de Mensagens e manda um e-mail com tudo junto."""
    today = today or notify.local_now().date()
    sent = 0
    for user in db.scalars(select(User)):
        if not user.email_verified or user.access_status != "approved":
            continue
        try:
            month = month_of(today, user.month_start_day)
            fresh = [
                a
                for a in month_alerts(db, user, month, today)
                if notify._claim(db, user, "alert", a["key"])
            ]
            if not fresh:
                continue
            for a in fresh:
                db.add(
                    InboxItem(user_id=user.id, kind="alert", title=a["title"][:160], body=a["text"])
                )
            db.commit()
            sent += 1
            from app.services import push

            first = fresh[0]
            push.send(
                db,
                user,
                "alerts",
                first["title"] if len(fresh) == 1 else f"{len(fresh)} alertas no seu orçamento",
                first["text"] if len(fresh) == 1 else first["title"],
                "/mensagens",
            )
            if user.notify_alerts:
                message = notify.Message(
                    subject="Alertas do seu orçamento"
                    if len(fresh) > 1
                    else fresh[0]["title"][:200],
                    heading="Alertas do seu orçamento",
                    intro="Encontramos movimentos que merecem atenção:",
                    sections=[
                        notify.Section(
                            title=a["title"],
                            note="" if user.notify_hide_values else a["text"],
                        )
                        for a in fresh
                    ],
                    button=("Abrir no app", notify._link("/mensagens")),
                    unsubscribe_kind="alerts",
                )
                text, body_html, headers = notify.render(message, user)
                mail(user.email, message.subject, text, body_html, headers)
                db.commit()
        except Exception as exc:  # um usuário com problema não impede os outros
            db.rollback()
            logger.exception("Alertas falharam para %s: %s", user.id, exc)
    return sent
