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
