"""Consultor financeiro: leitura do mês em linguagem simples, alertas e tendências.

As regras ficam aqui (e não na tela) para serem testadas e iguais em qualquer cliente.
O tom acompanha a situação: elogio para quem guardou, atenção para quem gastou quase
tudo e preocupação (sem bronca) para quem fechou no vermelho.
"""

import uuid
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.months import add_months, format_month
from app.models import Expense, Income, User
from app.services import analysis, budget, investments, planned

ZERO = Decimal("0.00")
AVERAGE_WINDOW = 3
# Categoria "fora do padrão": 30% acima da própria média e pelo menos R$ 50 de diferença.
CATEGORY_JUMP = Decimal("1.30")
CATEGORY_MIN_DIFF = Decimal("50")
LIMIT_WARNING_PCT = 80.0
DUE_SOON_DAYS = 7

IN_PROGRESS_HEADLINES = {
    "great": "Mês indo muito bem",
    "good": "Mês no caminho certo",
    "attention": "Atenção ao resto do mês",
}

MONTH_NAMES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]  # fmt: skip


def brl(value: Decimal) -> str:
    """R$ 1.234,56 (valor absoluto; o texto diz se é a mais ou a menos)."""
    text = f"{abs(value):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {text}"


def pct(value: float) -> str:
    return f"{value:.0f}%"


def num(value: float) -> str:
    return f"{value:.1f}".replace(".", ",")


def month_name(month: date) -> str:
    return f"{MONTH_NAMES[month.month - 1]} de {month.year}"


def _message(tone: str, title: str, text: str, **extra: Any) -> dict[str, Any]:
    return {"tone": tone, "title": title, "text": text, **extra}


def _category_totals(
    db: Session, user: User, start: date, end: date
) -> dict[date, dict[uuid.UUID | None, Decimal]]:
    rows = db.execute(
        select(Expense.month, Expense.category_id, func.sum(Expense.amount))
        .where(Expense.user_id == user.id, Expense.month.between(start, end))
        .group_by(Expense.month, Expense.category_id)
    )
    totals: dict[date, dict[uuid.UUID | None, Decimal]] = defaultdict(dict)
    for month, category_id, total in rows:
        totals[month][category_id] = Decimal(total)
    return totals


def _average(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return (sum(values, ZERO) / len(values)).quantize(Decimal("0.01"))


# ---------------------------------------------------------------- consultor


def consultant(db: Session, user: User, month: date, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    data = budget.get_month(db, user, month)
    summary = data.summary
    income: Decimal = summary["income_total"]
    expenses: Decimal = summary["expense_total"]
    balance: Decimal = summary["balance"]

    if income <= 0 and expenses <= 0:
        return {
            "month": format_month(month),
            "mood": "empty",
            "headline": "Vamos começar?",
            "summary": (
                f"Ainda não há lançamentos em {month_name(month)}. Cadastre sua renda e suas "
                "contas (as que se repetem todo mês podem ir em Contas fixas) e eu passo a "
                "acompanhar seus números por aqui."
            ),
            "savings_pct": None,
            "in_progress": False,
            "messages": [],
            "alerts": [],
        }

    history = budget.history(db, user, add_months(month, -1), 12)
    previous = [p for p in history if p["has_data"]]
    recent = previous[-AVERAGE_WINDOW:]
    savings_pct = float(balance / income * 100) if income > 0 else None

    messages: list[dict[str, Any]] = []
    alerts: list[dict[str, Any]] = []

    # 1. Resultado do mês
    if income <= 0:
        mood = "concern"
        headline = "Sem renda lançada neste mês"
        text = (
            f"Há {brl(expenses)} em contas e nenhuma renda registrada. Se você recebeu algo, "
            "lance para eu conseguir avaliar o mês."
        )
    elif balance < 0:
        mood = "concern"
        headline = "Este mês fechou no vermelho"
        text = (
            f"As contas passaram a renda em {brl(balance)}. Acontece, mas vale entender o "
            "motivo: veja abaixo onde os gastos subiram e o que dá para segurar no próximo mês."
        )
    elif savings_pct is not None and savings_pct >= 20:
        mood = "great"
        headline = "Mês excelente!"
        text = (
            f"Você guardou {pct(savings_pct)} da renda ({brl(balance)}). Isso está acima dos "
            "20% recomendados. Se ainda não fez, separe esse valor para a reserva ou para "
            "suas metas antes que ele se misture aos gastos."
        )
    elif savings_pct is not None and savings_pct >= 10:
        mood = "good"
        headline = "Bom mês"
        text = (
            f"Sobraram {brl(balance)} ({pct(savings_pct)} da renda). Está no caminho certo; "
            "chegar a 20% deixaria você mais protegido para imprevistos."
        )
    else:
        mood = "attention"
        headline = "Mês no limite"
        text = (
            f"Sobraram só {brl(balance)} ({pct(savings_pct or 0)} da renda). Qualquer "
            "imprevisto vira dívida. Vale revisar os gastos não essenciais."
        )
    result_summary = text

    # Mês em andamento: o resultado é parcial (ainda faltam gastos), então o tom é "até agora".
    in_progress = month.year == today.year and month.month == today.month
    if in_progress and mood != "concern":
        headline = IN_PROGRESS_HEADLINES[mood]
        result_summary = (
            f"Até agora, {text[0].lower()}{text[1:]} O mês ainda não acabou: os números "
            "mudam conforme novos gastos forem lançados."
        )

    # 2. Comparação com a própria média
    average_expenses = _average([p["expenses"] for p in recent])
    if average_expenses and average_expenses > 0:
        change = float((expenses - average_expenses) / average_expenses * 100)
        if change >= 10:
            messages.append(
                _message(
                    "warning",
                    f"Gastos {pct(change)} acima da sua média",
                    f"Você costuma gastar {brl(average_expenses)} por mês (média dos últimos "
                    f"{len(recent)} meses) e neste mês foram {brl(expenses)}.",
                )
            )
        elif change <= -10:
            messages.append(
                _message(
                    "praise",
                    f"Gastou {pct(-change)} menos que a média",
                    f"Foram {brl(expenses)}, contra a média de {brl(average_expenses)}. "
                    "Economia de verdade: parabéns!",
                )
            )

    # 3. Sequência de meses no azul (contando o atual)
    if balance >= 0 and income > 0:
        streak = 1
        for point in reversed(previous):
            if point["month"] != add_months(month, -streak) or point["balance"] < 0:
                break
            streak += 1
        if streak >= 3:
            messages.append(
                _message(
                    "praise",
                    f"{streak} meses seguidos no azul",
                    "Constância é o que mais faz diferença nas finanças. Continue assim!",
                )
            )
    elif balance < 0:
        negatives = sum(1 for p in recent if p["balance"] < 0)
        if negatives >= 1:
            messages.append(
                _message(
                    "danger",
                    "Mais de um mês negativo recentemente",
                    "Quando o vermelho se repete, a diferença costuma ir para o cartão ou o "
                    "cheque especial, que têm os juros mais altos. Se for o caso, priorize "
                    "quitar essas dívidas antes de qualquer outra meta.",
                )
            )

    # 4. Categorias: limites definidos pelo usuário e saltos em relação à média
    category_names = {c.id: c.name for c in budget.list_categories(db, user)}
    for item in summary["by_category"]:
        limit, used = item.get("limit"), item.get("limit_pct")
        if not limit or used is None:
            continue
        if used >= 100:
            alerts.append(
                _message(
                    "danger",
                    f"Limite de {item['name']} estourado",
                    f"{brl(item['total'])} de {brl(limit)} ({pct(used)}).",
                    category_id=item["category_id"],
                )
            )
        elif used >= LIMIT_WARNING_PCT:
            alerts.append(
                _message(
                    "warning",
                    f"{item['name']} perto do limite",
                    f"Já usou {pct(used)} ({brl(item['total'])} de {brl(limit)}). "
                    f"Restam {brl(limit - item['total'])} para o mês.",
                    category_id=item["category_id"],
                )
            )

    window_start = add_months(month, -AVERAGE_WINDOW)
    by_month = _category_totals(db, user, window_start, add_months(month, -1))
    months_with_data = [m for m in by_month if by_month[m]]
    jumps = []
    if months_with_data:
        for item in summary["by_category"]:
            past = [by_month[m].get(item["category_id"], ZERO) for m in months_with_data]
            avg = _average(past) or ZERO
            if avg > 0 and item["total"] >= avg * CATEGORY_JUMP:
                if item["total"] - avg >= CATEGORY_MIN_DIFF:
                    jumps.append((item["total"] - avg, item, avg))
    for diff, item, avg in sorted(jumps, key=lambda j: j[0], reverse=True)[:2]:
        name = category_names.get(item["category_id"], item["name"])
        alerts.append(
            _message(
                "warning",
                f"{name} acima do normal",
                f"{brl(item['total'])} neste mês, {brl(diff)} a mais que a sua média ({brl(avg)}).",
                category_id=item["category_id"],
            )
        )

    # 5. Renda quase toda comprometida (sem estar no vermelho)
    committed = summary["committed_pct"]
    if committed is not None and 90 <= committed <= 100:
        alerts.append(
            _message(
                "warning",
                "Orçamento quase estourado",
                f"{pct(committed)} da renda já está comprometida com contas. Evite novos "
                "gastos até o fim do mês.",
            )
        )

    # 6. Contas atrasadas e vencendo
    unpaid = [e for e in data.expenses if not e.paid and e.due_date]
    overdue = [e for e in unpaid if e.due_date < today]
    if overdue:
        total = sum((e.amount for e in overdue), ZERO)
        names = ", ".join(e.description for e in overdue[:3])
        alerts.append(
            _message(
                "danger",
                f"{len(overdue)} conta(s) em atraso",
                f"{names}{'…' if len(overdue) > 3 else ''}, somando {brl(total)}. Atrasos "
                "geram multa e juros: pague ou marque como paga se já pagou.",
            )
        )
    soon = [e for e in unpaid if today <= e.due_date <= today + timedelta(days=DUE_SOON_DAYS)]
    if soon:
        total = sum((e.amount for e in soon), ZERO)
        alerts.append(
            _message(
                "info",
                f"{len(soon)} conta(s) vencendo nos próximos {DUE_SOON_DAYS} dias",
                f"Somam {brl(total)}.",
            )
        )

    # 6b. Gastos planejados chegando (lembrete)
    upcoming = planned.pending_planned(db, user, today, today + timedelta(days=DUE_SOON_DAYS))
    if upcoming:
        first = upcoming[0]
        total = sum((p.amount for p in upcoming), ZERO)
        alerts.append(
            _message(
                "info",
                f"{len(upcoming)} gasto(s) planejado(s) nos próximos {DUE_SOON_DAYS} dias",
                f"Dia {first.date.day:02d}: {first.description} ({brl(first.amount)})"
                + (f" e mais {len(upcoming) - 1}" if len(upcoming) > 1 else "")
                + f". Total previsto: {brl(total)}. Lance quando acontecer, no Calendário.",
            )
        )

    # 6c. Renda variável: planejar pela média, não pelo melhor mês
    variable = [i for i in data.incomes if i.income_type == "variable"]
    if variable and income > 0:
        variable_total = sum((i.amount for i in variable), ZERO)
        share = float(variable_total / income * 100)
        past = list(
            db.execute(
                select(Income.month, func.sum(Income.amount))
                .where(
                    Income.user_id == user.id,
                    Income.income_type == "variable",
                    Income.month < month,
                    Income.month >= add_months(month, -6),
                )
                .group_by(Income.month)
            )
        )
        avg = _average([Decimal(total) for _, total in past])
        text = f"{pct(share)} da sua renda deste mês é variável ({brl(variable_total)})."
        if avg is not None:
            text += f" Sua média recente é {brl(avg)}"
            text += (
                ": este mês veio acima, bom momento para guardar a diferença."
                if variable_total > avg
                else ": planeje as contas fixas pela média, não pelo melhor mês."
            )
        else:
            text += " Planeje as contas fixas contando só com a parte fixa."
        alerts.append(_message("info", "Renda variável", text))

    # 7. Próximo mês (fixas + parcelas já lançadas + planejados)
    nxt = analysis.projection(db, user, add_months(month, 1), 1)[0]
    if nxt["income"] > 0 and nxt["balance"] < 0:
        alerts.append(
            _message(
                "warning",
                "Próximo mês tende a fechar no vermelho",
                "Só com as contas fixas, parcelas e gastos planejados, faltariam "
                f"{brl(nxt['balance'])}.",
            )
        )

    # 8. Reserva de emergência
    # Mesma base do score (média dos últimos meses com gastos), para os números baterem.
    reserve = investments.emergency_reserve_total(db, user)
    base = analysis.average_expenses(
        budget.history(db, user, month, analysis.CONSISTENCY_WINDOW), expenses
    )
    if base > 0:
        reserve_months = float(reserve / base)
        if reserve <= 0:
            messages.append(
                _message(
                    "info",
                    "Comece sua reserva de emergência",
                    f"O ideal é guardar de 3 a 6 meses de gastos ({brl(base * 3)} a "
                    f"{brl(base * 6)}) num investimento de resgate rápido, como o Tesouro "
                    "Selic ou um CDB com liquidez diária.",
                )
            )
        elif reserve_months >= 6:
            messages.append(
                _message(
                    "praise",
                    "Reserva de emergência completa",
                    f"Ela cobre {num(reserve_months)} meses de gastos. Daqui em diante, o que "
                    "sobrar pode ir para objetivos de prazo mais longo.",
                )
            )
        elif reserve_months < 3:
            messages.append(
                _message(
                    "info",
                    "Reserva ainda pequena",
                    f"Cobre {num(reserve_months)} meses de gastos; a meta é de 3 a 6.",
                )
            )

    # 9. Metas com prazo
    for goal in budget.list_goals(db, user):
        remaining = goal.target_amount - goal.current_amount
        if remaining <= 0:
            messages.append(
                _message("praise", f'Meta "{goal.name}" alcançada', "Objetivo cumprido!")
            )
            continue
        if not goal.target_date:
            continue
        months_left = (
            (goal.target_date.year - today.year) * 12 + goal.target_date.month - today.month
        )
        if months_left <= 0:
            alerts.append(
                _message(
                    "warning",
                    f'Prazo da meta "{goal.name}" chegou',
                    f"Faltam {brl(remaining)}. Que tal definir uma nova data?",
                )
            )
            continue
        needed = remaining / months_left
        if income > 0 and needed > max(balance, ZERO):
            alerts.append(
                _message(
                    "info",
                    f'Meta "{goal.name}" fora do ritmo',
                    f"Para chegar lá até {month_name(goal.target_date)}, seria preciso guardar "
                    f"{brl(needed)} por mês, mais do que sobrou agora ({brl(max(balance, ZERO))}).",
                )
            )

    order = {"danger": 0, "warning": 1, "info": 2, "praise": 3}
    alerts.sort(key=lambda a: order[a["tone"]])
    messages.sort(key=lambda m: order[m["tone"]])
    if not user.totp_enabled and not user.twofa_prompt_dismissed:
        # Por último e sem alarde: é uma sugestão, não uma obrigação.
        messages.append(
            _message(
                "info",
                "Dica de segurança",
                "Ative a verificação em duas etapas (em Segurança) para proteger seus dados "
                "financeiros mesmo que alguém descubra sua senha.",
            )
        )
    return {
        "month": format_month(month),
        "mood": mood,
        "headline": headline,
        "summary": result_summary,
        "savings_pct": round(savings_pct, 1) if savings_pct is not None else None,
        "in_progress": in_progress,
        "messages": messages,
        "alerts": alerts,
    }


# ---------------------------------------------------------------- tendências


def trends(db: Session, user: User, until: date, months: int = 12) -> dict[str, Any]:
    start = add_months(until, -(months - 1))
    points = budget.history(db, user, until, months)
    for point in points:
        point["savings_pct"] = (
            round(float(point["balance"] / point["income"] * 100), 1)
            if point["income"] > 0
            else None
        )

    # Evolução por categoria: as 5 maiores do período; o resto vira "Outras".
    by_month = _category_totals(db, user, start, until)
    categories = {c.id: c for c in budget.list_categories(db, user)}
    overall: dict[uuid.UUID | None, Decimal] = defaultdict(lambda: ZERO)
    for totals in by_month.values():
        for category_id, total in totals.items():
            overall[category_id] += total
    top = [cid for cid, _ in sorted(overall.items(), key=lambda kv: kv[1], reverse=True)[:5]]
    series = []
    for category_id in top:
        category = categories.get(category_id) if category_id else None
        series.append(
            {
                "category_id": category_id,
                "name": category.name if category else "Sem categoria",
                "color": category.color if category else None,
                "totals": [by_month.get(p["month"], {}).get(category_id, ZERO) for p in points],
            }
        )
    others = [
        sum((v for cid, v in by_month.get(p["month"], {}).items() if cid not in top), ZERO)
        for p in points
    ]
    if any(others):
        series.append({"category_id": None, "name": "Outras", "color": None, "totals": others})

    with_data = [p for p in points if p["has_data"]]

    def avg(key: str, window: int) -> Decimal | None:
        values = [p[key] for p in with_data[-window:]]
        return _average(values)

    last_year = add_months(until, -12)
    ly = budget.history(db, user, last_year, 1)[0]
    current = next(p for p in points if p["month"] == until)

    items = investments.list_investments(db, user)
    invested = sum((i.invested_amount for i in items), ZERO)
    current_value = sum((i.current_value for i in items), ZERO)
    goals = budget.list_goals(db, user)

    return {
        "months": points,
        "categories": series,
        "averages": {
            "income_3m": avg("income", 3),
            "expenses_3m": avg("expenses", 3),
            "balance_3m": avg("balance", 3),
            "income_6m": avg("income", 6),
            "expenses_6m": avg("expenses", 6),
            "balance_6m": avg("balance", 6),
        },
        "current": current,
        "same_month_last_year": ly,
        "wealth": {
            "invested": invested,
            "current": current_value,
            "return_value": current_value - invested,
            "reserve": investments.emergency_reserve_total(db, user),
        },
        "goals": {
            "count": len(goals),
            "target": sum((g.target_amount for g in goals), ZERO),
            "saved": sum((min(g.current_amount, g.target_amount) for g in goals), ZERO),
        },
    }
