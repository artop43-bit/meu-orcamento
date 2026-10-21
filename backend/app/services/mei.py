"""MEI (v1.4): faturamento do ano contra o teto e lembrete do DAS (conta fixa no dia 20)."""

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.months import today_local
from app.models import Income, User

# Teto anual de faturamento do MEI (Lei Complementar 123/2006, art. 18-A).
LIMIT = Decimal("81000.00")
WARN_PCT = 80.0


def summary(db: Session, user: User, year: int | None = None) -> dict[str, Any]:
    year = year or today_local().year
    total, count = db.execute(
        select(func.coalesce(func.sum(Income.amount), 0), func.count()).where(
            Income.user_id == user.id,
            Income.mei.is_(True),
            Income.month >= date(year, 1, 1),
            Income.month <= date(year, 12, 1),
        )
    ).one()
    total = Decimal(total)
    return {
        "year": year,
        "total": total,
        "limit": LIMIT,
        "pct": round(float(total / LIMIT * 100), 1),
        "count": count,
    }


def check_threshold(db: Session, user: User, year: int | None = None) -> bool:
    """Aviso uma vez por ano quando o faturamento passa de 80% do teto (caixa e aparelho)."""
    from app.models import InboxItem
    from app.services import notify, push

    data = summary(db, user, year)
    if data["pct"] < WARN_PCT or not notify._claim(db, user, "mei80", str(data["year"])):
        return False
    title = f"MEI: {data['pct']:.0f}% do teto anual"
    body = (
        f"O faturamento de {data['year']} chegou a {notify.brl(data['total'])} "
        f"de {notify.brl(data['limit'])}. Acima do teto, o MEI pode ser desenquadrado; "
        "vale conversar com um contador."
    )
    db.add(InboxItem(user_id=user.id, kind="alert", title=title, body=body))
    db.commit()
    push.send(db, user, "alerts", title, body[:200], "/ajustes/preferencias#mei")
    return True
