"""Saldo dia a dia do mês e "quanto posso gastar hoje".

O saldo começa em zero no dia 1 e soma cada renda no dia do recebimento (sem dia = dia 1),
tira cada conta no vencimento (sem data = dia 1) e os gastos planejados na data.
"""

import calendar as cal
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.months import with_day
from app.models import User
from app.services import budget, planned

ZERO = Decimal("0.00")


def forecast(db: Session, user: User, month: date, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    data = budget.get_month(db, user, month)
    last_day = cal.monthrange(month.year, month.month)[1]
    end = with_day(month, last_day)

    moves: dict[date, Decimal] = defaultdict(lambda: ZERO)
    for income in data.incomes:
        moves[with_day(month, income.day) if income.day else month] += income.amount
    for expense in data.expenses:
        day = (
            expense.due_date
            if expense.due_date and expense.due_date.replace(day=1) == month
            else month
        )
        moves[day] -= expense.amount
    pending_planned = planned.pending_planned(db, user, month, end)
    for item in pending_planned:
        moves[item.date] -= item.amount

    days = []
    balance = ZERO
    first_negative: date | None = None
    lowest = None
    for offset in range(last_day):
        day = month + timedelta(days=offset)
        balance += moves.get(day, ZERO)
        days.append({"date": day, "balance": balance, "change": moves.get(day, ZERO)})
        if balance < 0 and first_negative is None:
            first_negative = day
        if lowest is None or balance < lowest["balance"]:
            lowest = {"date": day, "balance": balance}

    result: dict[str, Any] = {
        "month": month,
        "days": days,
        "end_balance": balance,
        "lowest": lowest,
        "first_negative": first_negative,
        "planned_total": sum((p.amount for p in pending_planned), ZERO),
        "can_spend": None,
    }
    if month <= today <= end:
        # O que sobra no fim do mês, já tirando tudo o que está previsto, dividido pelos dias
        # que faltam (incluindo hoje). Se em algum dia o saldo ficar negativo, o limite é ele.
        remaining = min(balance, lowest["balance"] if lowest else balance)
        days_left = (end - today).days + 1
        per_day = (max(remaining, ZERO) / days_left).quantize(Decimal("0.01"))
        result["can_spend"] = {
            "today": per_day,
            "rest_of_month": max(remaining, ZERO),
            "days_left": days_left,
        }
    return result
