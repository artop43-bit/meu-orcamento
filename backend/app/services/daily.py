"""Saldo dia a dia do mês e "quanto posso gastar hoje".

O saldo começa em zero no 1º dia do mês financeiro (dia 1 ou o dia escolhido, ex.: o do salário)
e soma cada renda no dia do recebimento (sem dia = 1º dia), tira cada conta no vencimento (sem data
ou fora do período = 1º dia) e os gastos planejados na data.
"""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.months import cycle_date, cycle_range
from app.models import User
from app.services import budget, planned

ZERO = Decimal("0.00")


def forecast(db: Session, user: User, month: date, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    data = budget.get_month(db, user, month)
    start_day = user.month_start_day
    start, end = cycle_range(month, start_day)
    last_day = (end - start).days + 1

    moves: dict[date, Decimal] = defaultdict(lambda: ZERO)
    for income in data.incomes:
        moves[cycle_date(month, income.day, start_day) if income.day else start] += income.amount
    for expense in data.expenses:
        due = expense.due_date
        moves[due if due and start <= due <= end else start] -= expense.amount
    pending_planned = planned.pending_planned(db, user, month, end)
    for item in pending_planned:
        moves[item.date] -= item.amount

    days = []
    balance = ZERO
    first_negative: date | None = None
    lowest = None
    for offset in range(last_day):
        day = start + timedelta(days=offset)
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
