"""Contas dos empréstimos a amigos (v1.8): parcelas, juros e o caminho inverso (qual taxa dá o
lucro, a parcela ou o total que eu quero).

Tudo em funções puras (sem banco), para a simulação na tela e o empréstimo salvo usarem as
mesmas contas. Valores em Decimal com centavos; a última parcela fecha os centavos.

Formas de juros:
- "none": sem juros.
- "total": a taxa vale sobre o total (5% de R$ 1.000 = R$ 1.050), dividido em parcelas iguais.
- "simple": juros simples ao mês, proporcionais ao prazo, em parcelas iguais.
- "price": juros compostos ao mês, parcelas iguais (Tabela Price).
- "sac": juros compostos ao mês, devolução igual do valor e parcelas que diminuem (SAC).

Nas formas "simple", "price" e "sac" a taxa é ao mês; para pagamentos por dia, semana ou a cada
15 dias ela é convertida para o período (juros compostos pelo número de dias).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from app.core.months import add_months, with_day

Mode = Literal["none", "total", "simple", "price", "sac"]
Frequency = Literal["day", "week", "biweek", "month"]
Target = Literal["rate", "profit", "installment", "total"]

CENT = Decimal("0.01")
ZERO = Decimal("0")
MONTH_DAYS = 365.25 / 12
PERIOD_DAYS: dict[str, float] = {"day": 1, "week": 7, "biweek": 15, "month": MONTH_DAYS}
FREQUENCY_LABEL = {
    "day": "por dia",
    "week": "por semana",
    "biweek": "a cada 15 dias",
    "month": "por mês",
}
MODE_LABEL = {
    "none": "Sem juros",
    "total": "Sobre o total",
    "simple": "Simples ao mês",
    "price": "Compostos (Price)",
    "sac": "SAC",
}
# Lei da Usura (Decreto 22.626/33): limite comum entre particulares, 1% ao mês (12% ao ano).
USURY_MONTHLY = 1.0


def cents(value: Decimal | float) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass
class Row:
    number: int
    due_date: date
    amount: Decimal
    interest: Decimal
    principal: Decimal
    balance: Decimal  # quanto falta receber depois desta parcela

    def dump(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "due_date": self.due_date,
            "amount": self.amount,
            "interest": self.interest,
            "principal": self.principal,
            "balance": self.balance,
        }


def due_dates(first_due: date, count: int, frequency: Frequency) -> list[date]:
    if frequency == "month":
        start = first_due.replace(day=1)
        return [with_day(add_months(start, i), first_due.day) for i in range(count)]
    step = int(PERIOD_DAYS[frequency])
    return [first_due + timedelta(days=step * i) for i in range(count)]


def period_rate(monthly_pct: float, frequency: Frequency) -> float:
    """Taxa composta do período (fração) a partir da taxa ao mês (%)."""
    monthly = monthly_pct / 100
    if frequency == "month":
        return monthly
    return (1 + monthly) ** (PERIOD_DAYS[frequency] / MONTH_DAYS) - 1


def _equal(
    principal: Decimal, interest_total: Decimal, count: int
) -> tuple[list[Decimal], list[Decimal]]:
    """Parcelas iguais (a última fecha os centavos) e os juros de cada uma."""
    total = principal + interest_total
    each = cents(total / count)
    amounts = [each] * (count - 1) + [total - each * (count - 1)]
    share = cents(interest_total / count)
    interests = [share] * (count - 1) + [interest_total - share * (count - 1)]
    return amounts, interests


def schedule(
    principal: Decimal,
    mode: Mode,
    rate: float,
    count: int,
    frequency: Frequency,
    first_due: date,
) -> list[Row]:
    """Cronograma. `rate` em %: sobre o total no modo "total", ao mês nos demais."""
    principal = cents(principal)
    count = max(1, int(count))
    dates = due_dates(first_due, count, frequency)
    amounts: list[Decimal]
    interests: list[Decimal]
    if mode in ("none", "total", "simple"):
        if mode == "none":
            interest_total = ZERO
        elif mode == "total":
            interest_total = cents(principal * Decimal(str(rate)) / 100)
        else:
            months = count * PERIOD_DAYS[frequency] / MONTH_DAYS
            interest_total = cents(principal * Decimal(str(rate)) / 100 * Decimal(str(months)))
        amounts, interests = _equal(principal, interest_total, count)
    else:
        i = period_rate(rate, frequency)
        balance = float(principal)
        amounts, interests = [], []
        if mode == "price":
            pmt = (
                float(principal) / count
                if i == 0
                else float(principal) * i / (1 - (1 + i) ** -count)
            )
            for _ in range(count):
                interest = balance * i
                amortization = pmt - interest
                balance -= amortization
                amounts.append(cents(pmt))
                interests.append(cents(interest))
        else:  # sac
            amortization = float(principal) / count
            for _ in range(count):
                interest = balance * i
                amounts.append(cents(amortization + interest))
                interests.append(cents(interest))
                balance -= amortization
        # A soma das devoluções fecha exatamente o valor emprestado.
        principal_parts = [a - j for a, j in zip(amounts, interests, strict=True)]
        gap = principal - sum(principal_parts, ZERO)
        amounts[-1] += gap
    rows: list[Row] = []
    remaining = sum(amounts, ZERO)
    for number, (due, amount, interest) in enumerate(
        zip(dates, amounts, interests, strict=True), start=1
    ):
        remaining -= amount
        rows.append(Row(number, due, amount, interest, amount - interest, remaining))
    return rows


# ---------------------------------------------------------------- caminho inverso


def _metric(rows: list[Row], principal: Decimal, target: Target) -> float:
    total = float(sum((r.amount for r in rows), ZERO))
    if target == "profit":
        return total - float(principal)
    if target == "total":
        return total
    return float(rows[0].amount)  # "installment": a primeira parcela (no SAC é a maior)


def solve_rate(
    principal: Decimal,
    mode: Mode,
    count: int,
    frequency: Frequency,
    first_due: date,
    target: Target,
    value: Decimal,
) -> float | None:
    """A taxa (% sobre o total ou ao mês) que leva ao lucro, parcela ou total pedido."""
    principal = cents(principal)
    wanted = float(value)
    if mode == "none":
        return 0.0
    if target == "profit":
        profit = wanted
    elif target == "total":
        profit = wanted - float(principal)
    else:
        profit = None
    if profit is not None and profit < 0:
        return None
    if mode == "total" and profit is not None:
        return round(profit / float(principal) * 100, 6) if principal else None
    if mode == "simple" and profit is not None:
        months = count * PERIOD_DAYS[frequency] / MONTH_DAYS
        return (
            round(profit / (float(principal) * months) * 100, 6) if principal and months else None
        )
    # Busca binária na taxa: lucro, total e parcela crescem com ela.
    low, high = 0.0, 1000.0
    if (
        _metric(schedule(principal, mode, high, count, frequency, first_due), principal, target)
        < wanted
    ):
        return None
    if (
        _metric(schedule(principal, mode, low, count, frequency, first_due), principal, target)
        > wanted + 0.005
    ):
        return None
    for _ in range(80):
        mid = (low + high) / 2
        got = _metric(
            schedule(principal, mode, mid, count, frequency, first_due), principal, target
        )
        if got < wanted:
            low = mid
        else:
            high = mid
    return round(high, 6)


# ---------------------------------------------------------------- leitura do resultado


def equivalent_monthly(principal: Decimal, rows: list[Row], frequency: Frequency) -> float:
    """Taxa composta ao mês que iguala o valor emprestado às parcelas recebidas (TIR).
    A parcela k vence k períodos depois do empréstimo."""
    step = PERIOD_DAYS[frequency] / MONTH_DAYS
    flows = [(r.number * step, float(r.amount)) for r in rows]
    total = sum(v for _, v in flows)
    if total <= float(principal) + 0.004:
        return 0.0

    def npv(m: float) -> float:
        return sum(v / (1 + m) ** t for t, v in flows) - float(principal)

    low, high = 0.0, 10.0
    for _ in range(100):
        mid = (low + high) / 2
        if npv(mid) > 0:
            low = mid
        else:
            high = mid
    return high * 100


def start_date(first_due: date, frequency: Frequency) -> date:
    """Quando o dinheiro saiu: um período antes do primeiro pagamento."""
    if frequency == "month":
        return with_day(add_months(first_due.replace(day=1), -1), first_due.day)
    return first_due - timedelta(days=int(PERIOD_DAYS[frequency]))


def payback(rows: list[Row], principal: Decimal) -> int | None:
    """Número da parcela em que o valor emprestado já voltou inteiro."""
    received = ZERO
    for row in rows:
        received += row.amount
        if received >= principal:
            return row.number
    return None


def loss_if_stops(rows: list[Row], principal: Decimal, after: int) -> Decimal:
    """Quanto do valor emprestado se perde se a pessoa parar depois da parcela `after`."""
    received = sum((r.amount for r in rows[:after]), ZERO)
    return max(principal - received, ZERO)


def late_charge(
    amount: Decimal, days_late: int, fee_pct: float | None, interest_pct: float | None
) -> Decimal:
    """Multa fixa e juros de mora ao mês, proporcionais aos dias de atraso."""
    if days_late <= 0 or (not fee_pct and not interest_pct):
        return ZERO
    fee = float(amount) * (fee_pct or 0) / 100
    interest = float(amount) * (interest_pct or 0) / 100 * days_late / MONTH_DAYS
    return cents(fee + interest)


def summary(
    principal: Decimal,
    mode: Mode,
    rate: float,
    count: int,
    frequency: Frequency,
    first_due: date,
) -> dict[str, Any]:
    rows = schedule(principal, mode, rate, count, frequency, first_due)
    principal = cents(principal)
    total = sum((r.amount for r in rows), ZERO)
    monthly = equivalent_monthly(principal, rows, frequency)
    amounts = {r.amount for r in rows}
    middle = max(1, count // 2)
    return {
        "mode": mode,
        "rate": rate,
        "frequency": frequency,
        "count": count,
        "principal": principal,
        "total": total,
        "profit": total - principal,
        "installment": rows[0].amount,
        "last_installment": rows[-1].amount,
        "equal_installments": len(amounts) <= 2
        and abs(rows[0].amount - rows[-1].amount) <= Decimal("0.05"),
        "monthly_equivalent": round(monthly, 4),
        "yearly_equivalent": round(((1 + monthly / 100) ** 12 - 1) * 100, 2),
        "usury_warning": monthly > USURY_MONTHLY + 0.0005,
        "payback": payback(rows, principal),
        "stop_at": middle,
        "loss_if_stops": loss_if_stops(rows, principal, middle),
        "schedule": [r.dump() for r in rows],
    }


def compare(
    principal: Decimal,
    count: int,
    frequency: Frequency,
    first_due: date,
    profit: Decimal,
) -> list[dict[str, Any]]:
    """O mesmo lucro em cada forma de juros: a taxa a anunciar e as parcelas."""
    out = []
    for mode in ("total", "simple", "price", "sac"):
        rate = solve_rate(principal, mode, count, frequency, first_due, "profit", profit)
        if rate is None:
            continue
        rows = schedule(principal, mode, rate, count, frequency, first_due)
        out.append(
            {
                "mode": mode,
                "label": MODE_LABEL[mode],
                "rate": round(rate, 4),
                "first": rows[0].amount,
                "last": rows[-1].amount,
            }
        )
    return out


def market(
    principal: Decimal,
    profit: Decimal,
    months: float,
    cdi_year: float | None,
    ipca_year: float | None,
) -> dict[str, Any] | None:
    """Comparação com deixar o dinheiro aplicado e o lucro descontada a inflação."""
    if cdi_year is None and ipca_year is None:
        return None
    out: dict[str, Any] = {}
    if cdi_year is not None:
        gross = float(principal) * ((1 + cdi_year / 100) ** (months / 12) - 1)
        days = months * MONTH_DAYS
        tax = 0.225 if days <= 180 else 0.20 if days <= 360 else 0.175 if days <= 720 else 0.15
        out["cdi_year"] = cdi_year
        out["cdb_net"] = cents(gross * (1 - tax))
    if ipca_year is not None:
        factor = (1 + ipca_year / 100) ** (months / 12)
        out["ipca_year"] = ipca_year
        out["real_profit"] = cents((float(principal) + float(profit)) / factor - float(principal))
    return out
