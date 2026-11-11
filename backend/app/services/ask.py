"""Tire sua dúvida (v1.7): perguntas sobre os próprios dados, respondidas por regras.

Tudo roda aqui no servidor, sem serviço externo: a pergunta é lida por palavras-chave
(período, assunto e o que se quer saber) e a resposta sai das tabelas do próprio usuário.
A pergunta não é guardada.

Exemplos: "o que mais gastei esse mês?", "qual mês gastei mais esse ano?",
"quando gastei mais em mercado?", "quanto gastei com ifood em outubro?",
"onde encontro as recorrências?".
"""

import difflib
import re
import unicodedata
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.months import add_months, format_month, month_of, today_local, with_day
from app.models import Category, Expense, Goal, Income, Investment, OtherDebt, RecurringItem, User
from app.services import budget, cards, daily, goals, loans
from app.services.category_words import FALLBACK
from app.services.insights import MONTH_NAMES, brl
from app.services.suggest import keyword_category, normalize

MAX_QUESTION = 200
TOP = 5

SUGGESTIONS = [
    "O que mais gastei este mês?",
    "Qual mês gastei mais este ano?",
    "Quando gastei mais em alimentação?",
    "Quanto gastei com mercado no mês passado?",
    "O que vence nos próximos dias?",
    "Como estão minhas metas?",
    "Onde encontro as recorrências?",
]

# ---------------------------------------------------------------- textos


def _month_name(month: date, year: bool = True) -> str:
    name = MONTH_NAMES[month.month - 1]
    return f"{name} de {month.year}" if year else name


def _short_date(day: date) -> str:
    return f"{day.day:02d}/{day.month:02d}/{day.year}"


def _plain(text: str) -> str:
    """Minúsculas e sem acento, mantendo datas como "12/02" (o normalize do lançamento rápido
    apaga "2/10" por ser número de parcela)."""
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _cap(text: str) -> str:
    """Primeira letra maiúscula sem mexer no resto ("R$" continua "R$")."""
    return text[:1].upper() + text[1:]


def _plural(count: int, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


# ---------------------------------------------------------------- período

_DAY_NUMBERS = {
    "dois": 2,
    "tres": 3,
    "quatro": 4,
    "cinco": 5,
    "seis": 6,
    "sete": 7,
    "dez": 10,
    "quinze": 15,
    "trinta": 30,
}
_NUMBERS = {"dois": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "doze": 12}
_MONTHS = {normalize(name): i + 1 for i, name in enumerate(MONTH_NAMES)}
_THIS = r"(?:este|esse|neste|nesse|deste|desse|nesta|nessa|no|do)"


@dataclass
class Period:
    start: date
    end: date
    label: str  # "em novembro de 2026", "neste ano"...
    explicit: bool = True
    # Período em dias ("hoje", "esta semana", "dia 15"): filtra pela data do lançamento.
    day_start: date | None = None
    day_end: date | None = None

    @property
    def single(self) -> bool:
        return self.start == self.end

    def dump(self) -> dict[str, Any]:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "label": self.label,
            "day_start": self.day_start.isoformat() if self.day_start else None,
            "day_end": self.day_end.isoformat() if self.day_end else None,
        }

    @staticmethod
    def load(data: Any) -> "Period | None":
        try:
            return Period(
                date.fromisoformat(data["start"]),
                date.fromisoformat(data["end"]),
                str(data["label"])[:60],
                True,
                date.fromisoformat(data["day_start"]) if data.get("day_start") else None,
                date.fromisoformat(data["day_end"]) if data.get("day_end") else None,
            )
        except (KeyError, TypeError, ValueError, AttributeError):
            return None


def _days(first: date, last: date, label: str, start_day: int) -> Period:
    return Period(month_of(first, start_day), month_of(last, start_day), label, True, first, last)


def _parse_period(
    text: str, current: date, today: date | None = None, start_day: int = 1
) -> tuple[Period | None, str]:
    """Acha o período na pergunta e devolve o texto sem ele."""

    def cut(match: re.Match[str]) -> str:
        return (text[: match.start()] + " " + text[match.end() :]).strip()

    if today is not None:
        if m := re.search(r"\b(?:de |desde )?anteontem\b", text):
            day = today - timedelta(days=2)
            return _days(day, day, "anteontem", start_day), cut(m)
        if m := re.search(r"\b(?:de )?ontem\b", text):
            day = today - timedelta(days=1)
            return _days(day, day, "ontem", start_day), cut(m)
        if m := re.search(r"\b(?:de )?hoje\b", text):
            return _days(today, today, "hoje", start_day), cut(m)
        if m := re.search(r"\b(?:n?a |d?a )?semana passada\b|\bultima semana\b", text):
            monday = today - timedelta(days=today.weekday() + 7)
            return _days(monday, monday + timedelta(days=6), "na semana passada", start_day), cut(m)
        if m := re.search(r"\b(?:n?es[st]a|d?es[st]a|na|da) semana\b", text):
            monday = today - timedelta(days=today.weekday())
            return _days(monday, today, "nesta semana", start_day), cut(m)
        if m := re.search(
            r"\bultimos?\s+(\d{1,3}|dois|tres|quatro|cinco|seis|sete|dez|quinze|trinta)\s+dias\b",
            text,
        ):
            count = int(m[1]) if m[1].isdigit() else _DAY_NUMBERS[m[1]]
            count = max(1, min(count, 366))
            return _days(
                today - timedelta(days=count - 1), today, f"nos últimos {count} dias", start_day
            ), cut(m)
        if m := re.search(r"\b(?:n?o |em |de )?(?:dia )?(\d{1,2})/(\d{1,2})(?:/(20\d\d))?\b", text):
            try:
                year = int(m[3]) if m[3] else today.year
                day = date(year, int(m[2]), int(m[1]))
                if not m[3] and day > today:
                    day = date(year - 1, int(m[2]), int(m[1]))
                return _days(day, day, f"em {_short_date(day)}", start_day), cut(m)
            except ValueError:
                pass
        if m := re.search(r"\b(?:n?o |em |de )?dia (\d{1,2})\b", text):
            number = int(m[1])
            if 1 <= number <= 31:
                month = today.replace(day=1)
                if number > today.day:
                    month = add_months(month, -1)
                day = with_day(month, number)
                return _days(day, day, f"em {_short_date(day)}", start_day), cut(m)

    if m := re.search(r"\bultimos?\s+(\d{1,2}|dois|tres|quatro|cinco|seis|doze)\s+meses\b", text):
        count = int(m[1]) if m[1].isdigit() else _NUMBERS[m[1]]
        count = max(1, min(count, 36))
        return Period(
            add_months(current, -(count - 1)), current, f"nos últimos {count} meses"
        ), cut(m)
    if m := re.search(r"\b(?:no |do )?(?:mes passado|mes anterior|ultimo mes)\b", text):
        month = add_months(current, -1)
        return Period(month, month, f"em {_month_name(month)}"), cut(m)
    if m := re.search(r"\bano passado\b", text):
        year = current.year - 1
        return Period(date(year, 1, 1), date(year, 12, 1), f"em {year}"), cut(m)
    if m := re.search(rf"\b{_THIS}\s+ano\b|\bano atual\b", text):
        return Period(date(current.year, 1, 1), current, "neste ano"), cut(m)
    if m := re.search(rf"\b{_THIS}\s+mes\b|\bmes atual\b", text):
        return Period(current, current, "neste mês"), cut(m)
    names = "|".join(_MONTHS)
    if m := re.search(rf"\b(?:em |de |no mes de )?({names})(?:\s+(?:de\s+)?(20\d\d))?\b", text):
        number = _MONTHS[m[1]]
        year = int(m[2]) if m[2] else current.year - (1 if number > current.month else 0)
        month = date(year, number, 1)
        return Period(month, month, f"em {_month_name(month)}"), cut(m)
    if m := re.search(r"\b(?:em |de |no ano de )?(20\d\d)\b", text):
        year = int(m[1])
        end = min(date(year, 12, 1), current) if year == current.year else date(year, 12, 1)
        return Period(date(year, 1, 1), end, f"em {year}"), cut(m)
    return None, text


def _this_month(current: date) -> Period:
    return Period(current, current, "neste mês", explicit=False)


def _this_year(current: date) -> Period:
    return Period(date(current.year, 1, 1), current, "neste ano", explicit=False)


def _last_year(current: date) -> Period:
    return Period(add_months(current, -11), current, "nos últimos 12 meses", explicit=False)


# ---------------------------------------------------------------- assunto (categoria ou lugar)

_STOP = set(
    """
    o a os as um uma uns umas de do da dos das em no na nos nas com por pra para pro ao aos
    e ou que qual quais quanto quanta quantos quantas quando onde como foi foram fiz tive
    eu meu minha meus minhas me mim voce vc se ja ainda so mais menos muito pouco
    gastei gasto gastos gasta gastou gastamos gastar paguei pago pagar paga pagamento
    despesa despesas conta contas compra compras comprei valor valores total soma
    maior maiores mais caro cara caros caras alto alta altos altas ultimo ultima ultimos ultimas
    mes meses ano anos dia dias vez vezes categoria categorias lugar lugares loja lojas
    tenho tem tive teve ta esta estao estou sao era ser registrado registrada lancei lancado
    este esse isso isto aqui agora neste nesse pesou pesa sozinho sozinha la
    lancamento lancamentos saida saidas debito debitos algo alguma algum coisa coisas ate
    faltam falta ainda quanto quantas media medio mensal fiz feito feita foram total
    comparar compare comparacao comparado versus vs x contra entre do que
    saiu sairam parcela parcelas aberto abertas acabam acaba terminam termina devo
    """.split()
)


@dataclass
class Subject:
    label: str
    category_ids: list[uuid.UUID] = field(default_factory=list)
    text: str | None = None

    def condition(self) -> Any:
        if self.category_ids:
            return Expense.category_id.in_(self.category_ids)
        return None


def _subject_words(text: str) -> list[str]:
    return [w for w in re.split(r"[^a-z0-9&]+", text) if w and w not in _STOP and not w.isdigit()]


def _resolve_subject(db: Session, user: User, text: str) -> tuple[Subject | None, str | None]:
    """Categoria do usuário, palavra da descrição ou termo do dicionário. Devolve também o termo
    procurado quando nada combinou (para a resposta dizer o que não achou)."""
    words = _subject_words(text)
    if not words:
        return None, None
    phrase = " ".join(words)
    categories = list(db.scalars(select(Category).where(Category.user_id == user.id)))
    by_name = {normalize(c.name): c for c in categories}

    # 1. Nome de uma categoria do usuário (ou o começo dele: "aliment", "transportes").
    for name, category in sorted(by_name.items(), key=lambda kv: -len(kv[0])):
        name_words = name.split()
        if f" {name} " in f" {phrase} ":
            return Subject(category.name, [category.id]), None
        if any(
            len(w) >= 4
            and any(
                nw.startswith(w) or (w.startswith(nw) and len(w) - len(nw) <= 2)
                for nw in name_words
            )
            for w in words
        ):
            return Subject(category.name, [category.id]), None

    # 2. Palavra que aparece na descrição dos lançamentos ("ifood", "uber", "farmácia").
    for candidate in [phrase, *sorted(words, key=len, reverse=True)]:
        if len(candidate) < 3:
            continue
        found = db.scalar(
            select(Expense.description)
            .where(Expense.user_id == user.id, func.lower(Expense.description).contains(candidate))
            .limit(1)
        )
        if found is None:
            # Descrições com acento: compara sem acento (pouca linha, então em Python).
            descriptions = db.scalars(
                select(Expense.description).where(Expense.user_id == user.id).distinct().limit(3000)
            )
            found = next((d for d in descriptions if candidate in normalize(d)), None)
        if found is not None:
            return Subject(f"“{candidate}”", text=candidate), None

    # 3. Dicionário do lançamento rápido ("lanche" → Alimentação, "gasolina" → Transporte).
    name = keyword_category(phrase)
    for candidate in (name, FALLBACK.get(name or "")):
        if candidate and normalize(candidate) in by_name:
            category = by_name[normalize(candidate)]
            return Subject(category.name, [category.id]), None
    return None, phrase


def _matches(expense: Expense, subject: Subject | None) -> bool:
    if subject is None:
        return True
    if subject.category_ids:
        return expense.category_id in subject.category_ids
    return subject.text is not None and subject.text in normalize(expense.description)


def _expenses(db: Session, user: User, period: Period, subject: Subject | None) -> list[Expense]:
    start, end = period.start, period.end
    if period.day_start and period.day_end:
        # A data do lançamento pode cair num mês do orçamento vizinho (mês financeiro, fatura).
        start = add_months(min(start, period.day_start.replace(day=1)), -1)
        end = add_months(max(end, period.day_end.replace(day=1)), 2)
    query = select(Expense).where(Expense.user_id == user.id, Expense.month.between(start, end))
    if subject is not None and subject.condition() is not None:
        query = query.where(subject.condition())
    rows = [e for e in db.scalars(query) if _matches(e, subject)]
    if period.day_start and period.day_end:
        rows = [e for e in rows if period.day_start <= _when(e) <= period.day_end]
    return rows


def _when(expense: Expense) -> date:
    return expense.purchase_date or expense.due_date or expense.month


def _item(expense: Expense, categories: dict[uuid.UUID, str]) -> dict[str, Any]:
    detail = [_short_date(_when(expense))]
    if expense.category_id in categories:
        detail.append(categories[expense.category_id])
    if expense.installment_total:
        detail.append(f"parcela {expense.installment_number}/{expense.installment_total}")
    return {
        "label": expense.description,
        "detail": " · ".join(detail),
        "value": brl(expense.amount),
        "link": f"/orcamento/{format_month(expense.month)}",
    }


def _category_names(db: Session, user: User) -> dict[uuid.UUID, str]:
    return {c.id: c.name for c in db.scalars(select(Category).where(Category.user_id == user.id))}


# ---------------------------------------------------------------- respostas


def _answer(intent: str, answer: str, **extra: Any) -> dict[str, Any]:
    return {
        "intent": intent,
        "answer": answer,
        "items": [],
        "links": [],
        "suggestions": [],
        **extra,
    }


def _nothing(period: Period, subject: Subject | None) -> dict[str, Any]:
    about = f" com {subject.label}" if subject else ""
    return _answer(
        "empty",
        f"Não encontrei despesas{about} {period.label}.",
        suggestions=["O que mais gastei este ano?", "Quanto gastei nos últimos 3 meses?"],
    )


def _top_categories(db: Session, user: User, period: Period) -> dict[str, Any]:
    rows = _expenses(db, user, period, None)
    if not rows:
        return _nothing(period, None)
    names = _category_names(db, user)
    totals: dict[str, Decimal] = defaultdict(Decimal)
    for e in rows:
        totals[names.get(e.category_id, "Sem categoria") if e.category_id else "Sem categoria"] += (
            e.amount
        )
    total = sum(totals.values(), Decimal(0))
    ranking = sorted(totals.items(), key=lambda kv: -kv[1])
    first, value = ranking[0]
    biggest = max(rows, key=lambda e: e.amount)
    share = f"{value / total * 100:.0f}%" if total else "0%"
    answer = (
        f"{_cap(period.label)}, o que mais pesou foi {first}: {brl(value)} ({share} de {brl(total)}). "
        f"A maior despesa sozinha foi {biggest.description}, {brl(biggest.amount)} em {_short_date(_when(biggest))}."
    )
    items = [
        {
            "label": name,
            "detail": f"{v / total * 100:.0f}% do total" if total else "",
            "value": brl(v),
            "link": None,
        }
        for name, v in ranking[:TOP]
    ]
    return _answer(
        "top_categories",
        answer,
        items=items,
        links=[{"label": "Ver categorias nos Insights", "to": "/analises?secao=categorias"}],
        suggestions=[f"Quando gastei mais em {first.lower()}?", "Qual mês gastei mais este ano?"],
    )


def _month_max(db: Session, user: User, period: Period, subject: Subject | None) -> dict[str, Any]:
    if period.single:  # "qual mês" pede comparação: usa o ano do mês citado.
        period = Period(
            date(period.start.year, 1, 1), period.end, f"em {period.start.year}", period.explicit
        )
    rows = _expenses(db, user, period, subject)
    if not rows:
        return _nothing(period, subject)
    totals: dict[date, Decimal] = defaultdict(Decimal)
    for e in rows:
        totals[e.month] += e.amount
    ranking = sorted(totals.items(), key=lambda kv: -kv[1])
    month, value = ranking[0]
    average = sum(totals.values(), Decimal(0)) / len(totals)
    about = f" com {subject.label}" if subject else ""
    answer = f"{_cap(period.label)}, o mês em que você mais gastou{about} foi {_month_name(month)}: {brl(value)}."
    if len(totals) > 1:
        answer += (
            f" A média dos {_plural(len(totals), 'mês', 'meses')} com gastos foi {brl(average)}."
        )
    items = [
        {
            "label": _month_name(m).capitalize(),
            "detail": None,
            "value": brl(v),
            "link": f"/orcamento/{format_month(m)}",
        }
        for m, v in ranking[:TOP]
    ]
    return _answer(
        "month_max",
        answer,
        items=items,
        links=[{"label": f"Abrir {_month_name(month)}", "to": f"/orcamento/{format_month(month)}"}],
        suggestions=["Comparar dois meses", "O que mais gastei este mês?"]
        if subject is None
        else [],
    )


def _biggest(db: Session, user: User, period: Period, subject: Subject | None) -> dict[str, Any]:
    rows = _expenses(db, user, period, subject)
    if not rows:
        return _nothing(period, subject)
    names = _category_names(db, user)
    ranking = sorted(rows, key=lambda e: (-e.amount, _when(e)))[:TOP]
    top = ranking[0]
    about = f" com {subject.label}" if subject else ""
    answer = (
        f"Os maiores gastos{about} {period.label}: o maior foi {top.description}, "
        f"{brl(top.amount)} em {_short_date(_when(top))}."
    )
    total = sum((e.amount for e in rows), Decimal(0))
    if subject is not None:
        answer += (
            f" No total foram {brl(total)} em {_plural(len(rows), 'lançamento', 'lançamentos')}."
        )
    return _answer("biggest", answer, items=[_item(e, names) for e in ranking])


def _sum(db: Session, user: User, period: Period, subject: Subject | None) -> dict[str, Any]:
    rows = _expenses(db, user, period, subject)
    if not rows:
        return _nothing(period, subject)
    total = sum((e.amount for e in rows), Decimal(0))
    about = f" com {subject.label}" if subject else ""
    answer = f"{_cap(period.label)} você gastou {brl(total)}{about}, em {_plural(len(rows), 'lançamento', 'lançamentos')}."
    if not period.single:
        months = len({e.month for e in rows})
        answer += f" Média de {brl(total / months)} por mês com gasto."
    names = _category_names(db, user)
    ranking = sorted(rows, key=lambda e: -e.amount)[:3]
    return _answer(
        "sum",
        answer,
        items=[_item(e, names) for e in ranking] if subject else [],
        suggestions=[f"Quando gastei mais com {subject.label.strip('“”').lower()}?"]
        if subject
        else ["O que mais gastei este mês?"],
    )


def _last(db: Session, user: User, subject: Subject | None) -> dict[str, Any]:
    query = select(Expense).where(Expense.user_id == user.id)
    if subject is not None and subject.condition() is not None:
        query = query.where(subject.condition())
    rows = [
        e
        for e in db.scalars(query.order_by(Expense.created_at.desc()).limit(500))
        if _matches(e, subject)
    ]
    if not rows:
        return _answer(
            "empty", f"Ainda não há despesas{f' com {subject.label}' if subject else ''}."
        )
    rows.sort(key=lambda e: (_when(e), e.created_at), reverse=True)
    last = rows[0]
    about = f" com {subject.label}" if subject else ""
    names = _category_names(db, user)
    return _answer(
        "last",
        f"A última despesa{about} foi {last.description}, {brl(last.amount)} em {_short_date(_when(last))}.",
        items=[_item(e, names) for e in rows[:3]],
    )


def _incomes(db: Session, user: User, period: Period) -> dict[str, Any]:
    rows = list(
        db.scalars(
            select(Income).where(
                Income.user_id == user.id, Income.month.between(period.start, period.end)
            )
        )
    )
    if not rows:
        return _answer(
            "empty",
            f"Não há receitas lançadas {period.label}.",
            links=[{"label": "Lançar receita", "to": "/orcamento"}],
        )
    total = sum((i.amount for i in rows), Decimal(0))
    totals: dict[str, Decimal] = defaultdict(Decimal)
    for i in rows:
        totals[i.description] += i.amount
    ranking = sorted(totals.items(), key=lambda kv: -kv[1])[:TOP]
    return _answer(
        "incomes",
        f"{_cap(period.label)} entraram {brl(total)} em {_plural(len(rows), 'receita', 'receitas')}.",
        items=[
            {"label": name, "detail": None, "value": brl(v), "link": None} for name, v in ranking
        ],
    )


def _balance(db: Session, user: User, period: Period) -> dict[str, Any]:
    spent = db.scalar(
        select(func.coalesce(func.sum(Expense.amount), 0)).where(
            Expense.user_id == user.id, Expense.month.between(period.start, period.end)
        )
    )
    earned = db.scalar(
        select(func.coalesce(func.sum(Income.amount), 0)).where(
            Income.user_id == user.id, Income.month.between(period.start, period.end)
        )
    )
    spent, earned = Decimal(spent or 0), Decimal(earned or 0)
    result = earned - spent
    word = "sobraram" if result >= 0 else "faltaram"
    return _answer(
        "balance",
        f"{_cap(period.label)}: receitas {brl(earned)}, despesas {brl(spent)}. {word.capitalize()} {brl(result)}.",
        items=[
            {"label": "Receitas", "detail": None, "value": brl(earned), "link": None},
            {"label": "Despesas", "detail": None, "value": brl(spent), "link": None},
            {
                "label": "Saldo",
                "detail": None,
                "value": ("−" if result < 0 else "") + brl(result),
                "link": None,
            },
        ],
    )


def _cards(db: Session, user: User, today: date) -> dict[str, Any]:
    summary = [
        s for s in cards.summary(db, user, today) if s["available"] is not None or s["open_invoice"]
    ]
    if not summary:
        return _answer(
            "cards",
            "Você ainda não cadastrou cartão de crédito.",
            links=[{"label": "Cadastrar cartão", "to": "/cartoes"}],
        )
    items = []
    for s in summary:
        invoice = s["open_invoice"]
        detail = []
        if invoice:
            detail.append(f"fatura aberta {brl(invoice['total'])}")
        if s["available"] is not None:
            detail.append(f"disponível {brl(s['available'])}")
        items.append(
            {
                "label": s["card"].name,
                "detail": " · ".join(detail),
                "value": brl(s["used"]),
                "link": "/cartoes",
            }
        )
    used = sum((s["used"] for s in summary), Decimal(0))
    return _answer(
        "cards",
        f"Você tem {brl(used)} em compras ainda não pagas em {_plural(len(summary), 'cartão', 'cartões')}.",
        items=items,
        links=[{"label": "Abrir cartões", "to": "/cartoes"}],
    )


# ---------------------------------------------------------------- "onde encontro…"

PLACES: list[tuple[str, str, str]] = [
    (
        "Lançar uma despesa ou receita",
        "/orcamento",
        "lancar lancamento despesa receita adicionar nova novo cadastrar rapido orcamento gasto",
    ),
    ("Calendário de vencimentos", "/calendario", "calendario vencimento vencimentos datas agenda"),
    ("Cartões e faturas", "/cartoes", "cartao cartoes fatura faturas limite credito debito"),
    (
        "Contas e saldos",
        "/contas",
        "banco bancaria bancarias saldo saldos carteira transferencia transferir",
    ),
    (
        "Revisar lançamentos importados",
        "/revisar",
        "revisar conferir importados importado pendentes",
    ),
    ("Busca", "/busca", "busca buscar procurar pesquisar pesquisa"),
    (
        "Mensagens e avisos",
        "/mensagens",
        "mensagens mensagem notificacoes notificacao avisos lembretes",
    ),
    (
        "Dívidas e financiamentos",
        "/dividas",
        "divida dividas emprestimo emprestimos financiamento quitar",
    ),
    ("Divisões com outras pessoas", "/divisoes", "dividir divisao divisoes racha rachar amigos"),
    (
        "Metas e desafios",
        "/metas",
        "meta metas objetivo objetivos guardar poupar sonho desafio desafios",
    ),
    ("Histórico", "/historico", "historico anteriores antigos"),
    ("Insights", "/analises", "insights insight analise analises resumo graficos grafico"),
    (
        "Calculadoras",
        "/analises?secao=calculadoras",
        "calculadora calculadoras juros parcelamento parcelar parcela reserva emergencia",
    ),
    ("Projeção", "/analises?secao=projecao", "projecao previsao futuro proximos"),
    ("Simulador", "/analises?secao=simulador", "simulador simular simulacao"),
    ("Comparar meses", "/analises?secao=comparar", "comparar comparacao"),
    ("Saúde financeira", "/analises?secao=saude", "saude score nota regra 50/30/20"),
    (
        "Investimentos",
        "/investimentos",
        "investimento investimentos aplicacao aplicacoes cdb tesouro acoes rendimento",
    ),
    (
        "Recorrências (contas fixas)",
        "/ajustes/recorrencias",
        "recorrencia recorrencias fixa fixas assinatura assinaturas mensalidade",
    ),
    ("Categorias", "/ajustes/categorias", "categoria categorias teto"),
    (
        "Importar e exportar dados",
        "/ajustes/dados",
        "importar exportar backup planilha csv extrato ofx dados",
    ),
    ("Segurança e senha", "/ajustes/seguranca", "senha seguranca fatores 2fa sessoes"),
    (
        "Preferências e aparência",
        "/ajustes/preferencias",
        "tema cor cores aparencia estilo escuro claro glass preferencias atalhos",
    ),
    ("Perfil", "/ajustes/perfil", "perfil nome foto email"),
    (
        "Solicitações e suporte",
        "/ajustes/solicitacoes",
        "suporte problema sugestao sugestoes solicitacao solicitacoes erro",
    ),
    ("Ajuda", "/ajustes/ajuda", "ajuda tutorial usar"),
    ("Novidades da versão", "/ajustes/notas", "novidades versao atualizacao notas"),
    ("Instalar o app", "/ajustes/app", "app aplicativo instalar celular android"),
    ("Relatório do mês", "/relatorio", "relatorio imprimir pdf"),
]

_NAV_STOP = _STOP | set(
    "encontro encontrar acho achar fica ficam vejo ver posso faco fazer mudo mudar altero alterar troco trocar crio criar cadastro adiciono".split()
)


def _places(text: str) -> list[tuple[int, str, str]]:
    words = [w for w in re.split(r"[^a-z0-9/]+", text) if len(w) >= 3 and w not in _NAV_STOP]
    found = []
    for label, path, keys in PLACES:
        terms = keys.split()
        score = 0
        for w in words:
            if w in terms:
                score += 3
            elif len(w) >= 5 and any(t.startswith(w[:5]) for t in terms):
                score += 1
        if score:
            found.append((score, label, path))
    return sorted(found, key=lambda t: -t[0])


def _navigate(text: str) -> dict[str, Any] | None:
    found = _places(text)
    if not found:
        return None
    best = found[0][0]
    top = [f for f in found if f[0] >= best - 1][:3]
    first = top[0]
    return _answer(
        "navigate",
        f"Fica em {first[1]}." if len(top) == 1 else f"Pode ser em {first[1]} ou nestes lugares:",
        links=[{"label": label, "to": path} for _, label, path in top],
    )


# ---------------------------------------------------------------- temas novos (v1.7.5)


def _due(db: Session, user: User, today: date, only_late: bool = False) -> dict[str, Any]:
    until = today + timedelta(days=10)
    rows = list(
        db.scalars(
            select(Expense)
            .where(
                Expense.user_id == user.id,
                Expense.paid.is_(False),
                Expense.due_date.is_not(None),
                Expense.due_date <= until,
            )
            .order_by(Expense.due_date)
            .limit(200)
        )
    )
    late = [e for e in rows if e.due_date and e.due_date < today]
    soon = [] if only_late else [e for e in rows if e.due_date and e.due_date >= today]
    names = _category_names(db, user)

    def total(items: list[Expense]) -> str:
        return brl(sum((e.amount for e in items), Decimal(0)))

    if only_late and not late:
        return _answer(
            "due",
            "Nenhuma conta atrasada. 👍",
            links=[{"label": "Abrir o calendário", "to": "/calendario"}],
        )
    if not late and not soon:
        return _answer("due", "Nada vencendo nos próximos 10 dias e nenhuma conta atrasada. 👍")
    parts = []
    if soon:
        parts.append(
            f"{_plural(len(soon), 'conta vence', 'contas vencem')} nos próximos 10 dias ({total(soon)})"
        )
    if late:
        parts.append(
            f"{_plural(len(late), 'conta está atrasada', 'contas estão atrasadas')} ({total(late)})"
        )
    items = []
    for e in (late + soon)[:8]:
        item = _item(e, names)
        assert e.due_date is not None
        item["detail"] = (
            "atrasada · " if e.due_date < today else ""
        ) + f"vence {_short_date(e.due_date)}"
        items.append(item)
    return _answer(
        "due",
        _cap(" e ".join(parts)) + ".",
        items=items,
        links=[{"label": "Abrir o calendário", "to": "/calendario"}],
    )


def _goals(db: Session, user: User, today: date | None = None) -> dict[str, Any]:
    found = list(
        db.scalars(
            select(Goal)
            .where(Goal.user_id == user.id)
            .order_by(Goal.is_main.desc(), Goal.created_at)
        )
    )
    if not found:
        return _answer(
            "goals",
            "Você ainda não tem metas.",
            links=[{"label": "Criar uma meta", "to": "/metas"}],
        )
    items = []
    sentences = []
    for g in found[:TOP]:
        proj = goals.projection(db, user, g, today)
        pct = int(g.current_amount / g.target_amount * 100) if g.target_amount else 0
        if proj["status"] == "completed":
            detail = "concluída 🎉"
            sentence = f"{g.name} já foi concluída"
        else:
            detail = f"faltam {brl(proj['remaining'])} · {pct}%"
            sentence = (
                f"para {g.name} faltam {brl(proj['remaining'])} ({pct}% de {brl(g.target_amount)})"
            )
            if proj.get("eta"):
                detail += f" · previsão {_month_name(proj['eta'])}"
                sentence += f"; no ritmo atual você chega lá em {_month_name(proj['eta'])}"
            elif proj.get("required_monthly"):
                sentence += f"; precisa guardar {brl(proj['required_monthly'])} por mês"
        sentences.append(sentence)
        items.append(
            {"label": g.name, "detail": detail, "value": brl(g.current_amount), "link": "/metas"}
        )
    return _answer(
        "goals",
        _cap("; ".join(sentences[:2])) + ".",
        items=items,
        links=[{"label": "Abrir metas", "to": "/metas"}],
    )


def _invoices(db: Session, user: User, today: date) -> dict[str, Any]:
    summary = [s for s in cards.summary(db, user, today) if s["open_invoice"]]
    if not summary:
        return _answer(
            "cards",
            "Você ainda não cadastrou cartão de crédito.",
            links=[{"label": "Cadastrar cartão", "to": "/cartoes"}],
        )
    rows = []
    for s in summary:
        for invoice in (s["closed_invoice"], s["open_invoice"]):
            if (
                invoice
                and invoice["status"] != "paid"
                and (invoice["total"] or invoice is s["open_invoice"])
            ):
                rows.append((invoice["due_date"], s["card"].name, invoice))
    rows.sort(key=lambda r: r[0])
    status = {"open": "aberta", "closed": "fechada", "overdue": "vencida", "paid": "paga"}
    items = [
        {
            "label": name,
            "detail": f"fatura {status[inv['status']]} · fecha {_short_date(inv['closing_date'])} · vence {_short_date(due)}",
            "value": brl(inv["total"]),
            "link": "/cartoes",
        }
        for due, name, inv in rows[:6]
    ]
    if not rows:
        return _answer(
            "invoices",
            "Nenhuma fatura em aberto. 👍",
            links=[{"label": "Abrir cartões", "to": "/cartoes"}],
        )
    due, name, first = rows[0]
    return _answer(
        "invoices",
        f"A próxima fatura a vencer é a do {name}: {brl(first['total'])}, vence em {_short_date(due)} (fecha em {_short_date(first['closing_date'])}).",
        items=items,
        links=[{"label": "Abrir cartões", "to": "/cartoes"}],
    )


def _can_spend(db: Session, user: User, today: date, current: date) -> dict[str, Any]:
    data = daily.forecast(db, user, current, today)
    can = data.get("can_spend")
    links = [{"label": "Abrir o Orçamento", "to": "/orcamento"}]
    if not can:
        return _answer(
            "can_spend",
            f"O saldo previsto para o fim do mês é {('−' if data['end_balance'] < 0 else '') + brl(data['end_balance'])}.",
            links=links,
        )
    if can["rest_of_month"] <= 0:
        text = "Hoje não há saldo livre: as despesas previstas consomem toda a receita do mês."
        if data.get("first_negative"):
            text += f" O saldo fica negativo a partir de {_short_date(data['first_negative'])}."
        return _answer("can_spend", text, links=links)
    return _answer(
        "can_spend",
        f"Hoje você pode gastar até {brl(can['today'])}. São {brl(can['rest_of_month'])} livres até o fim do mês, em {_plural(can['days_left'], 'dia', 'dias')}, já descontando tudo o que está previsto.",
        links=links,
    )


def _installments(
    db: Session, user: User, current: date, subject: Subject | None
) -> dict[str, Any]:
    rows = [
        e
        for e in db.scalars(
            select(Expense).where(
                Expense.user_id == user.id,
                Expense.installment_group_id.is_not(None),
                Expense.month >= current,
            )
        )
        if _matches(e, subject)
    ]
    about = f" de {subject.label}" if subject else ""
    if not rows:
        return _answer("installments", f"Não há parcelas em aberto{about}. 👍")
    groups: dict[uuid.UUID, list[Expense]] = defaultdict(list)
    for e in rows:
        assert e.installment_group_id is not None
        groups[e.installment_group_id].append(e)
    items = []
    total = Decimal(0)
    for group in sorted(groups.values(), key=lambda g: -sum((e.amount for e in g), Decimal(0))):
        left = [e for e in group if not e.paid]
        if not left:
            continue
        amount = sum((e.amount for e in left), Decimal(0))
        total += amount
        last = max(left, key=lambda e: e.month)
        name = re.sub(r"\s*\(?\d+\s*/\s*\d+\)?\s*$", "", left[0].description)
        items.append(
            {
                "label": name,
                "detail": f"faltam {_plural(len(left), 'parcela', 'parcelas')} de {brl(left[0].amount)} · até {_month_name(last.month)}",
                "value": brl(amount),
                "link": f"/orcamento/{format_month(min(e.month for e in left))}",
            }
        )
    if not items:
        return _answer("installments", f"Não há parcelas em aberto{about}. 👍")
    first = items[0]
    text = (
        f"{first['label']}: {first['detail']} ({first['value']} no total)."
        if len(items) == 1
        else f"Você tem {len(items)} compras parceladas em aberto, somando {brl(total)}. A maior é {first['label']}: {first['detail']}."
    )
    return _answer("installments", text, items=items[:6])


def _loans(db: Session, user: User) -> dict[str, Any]:
    items = []
    total = Decimal(0)
    for loan in loans.list_loans(db, user):
        info = loans.summary(db, loan)
        total += info["balance"]
        detail = f"{info['paid_installments']}/{loan.installments} parcelas pagas"
        if info["next_payment"] is not None and info["next_due"]:
            detail += f" · próxima {brl(info['next_payment'])} em {_short_date(info['next_due'])}"
        items.append(
            {
                "label": loan.name,
                "detail": detail,
                "value": brl(info["balance"]),
                "link": "/dividas",
            }
        )
    for debt in db.scalars(select(OtherDebt).where(OtherDebt.user_id == user.id)):
        total += debt.balance
        items.append(
            {
                "label": debt.name,
                "detail": "outra dívida",
                "value": brl(debt.balance),
                "link": "/dividas",
            }
        )
    if not items:
        return _answer(
            "loans",
            "Você não tem financiamentos nem dívidas cadastradas.",
            links=[{"label": "Abrir dívidas", "to": "/dividas"}],
        )
    return _answer(
        "loans",
        f"O saldo devedor é de {brl(total)} em {_plural(len(items), 'contrato', 'contratos')}.",
        items=items[:6],
        links=[{"label": "Abrir dívidas", "to": "/dividas"}],
    )


def _recurring(db: Session, user: User, current: date, only_subscriptions: bool) -> dict[str, Any]:
    names = _category_names(db, user)
    rows = [
        r
        for r in db.scalars(
            select(RecurringItem).where(
                RecurringItem.user_id == user.id, RecurringItem.kind == "expense"
            )
        )
        if budget.active_in(r, current) or (r.end_month is None or r.end_month >= current)
    ]
    if only_subscriptions:
        subs = [
            r
            for r in rows
            if normalize(names.get(r.category_id, "")) == "assinaturas"
            or keyword_category(r.description) == "Assinaturas"
            or re.search(_SUBSCRIPTION, normalize(r.description))
        ]  # type: ignore[arg-type]
        rows = subs
    label = "assinaturas" if only_subscriptions else "despesas fixas"
    if not rows:
        return _answer(
            "recurring",
            f"Não encontrei {label} nas recorrências.",
            links=[{"label": "Abrir recorrências", "to": "/ajustes/recorrencias"}],
        )
    monthly = sum((r.amount / max(r.interval_months or 1, 1) for r in rows), Decimal(0))
    rows.sort(key=lambda r: -r.amount)
    items = [
        {
            "label": r.description,
            "detail": " · ".join(
                x
                for x in (
                    names.get(r.category_id) if r.category_id else None,
                    f"dia {r.due_day}" if r.due_day else None,
                    None if (r.interval_months or 1) == 1 else f"a cada {r.interval_months} meses",
                )
                if x
            ),
            "value": brl(r.amount),
            "link": "/ajustes/recorrencias",
        }
        for r in rows[:8]
    ]
    return _answer(
        "recurring",
        f"Você tem {len(rows)} {label}, somando {brl(monthly)} por mês.",
        items=items,
        links=[{"label": "Abrir recorrências", "to": "/ajustes/recorrencias"}],
    )


def _investments(db: Session, user: User) -> dict[str, Any]:
    rows = list(db.scalars(select(Investment).where(Investment.user_id == user.id)))
    if not rows:
        return _answer(
            "investments",
            "Você ainda não cadastrou investimentos.",
            links=[{"label": "Abrir investimentos", "to": "/investimentos"}],
        )
    invested = sum((r.invested_amount for r in rows), Decimal(0))
    value = sum((r.current_value for r in rows), Decimal(0))
    gain = value - invested
    pct = f" ({gain / invested * 100:+.1f}%)".replace(".", ",") if invested else ""
    rows.sort(key=lambda r: -r.current_value)
    return _answer(
        "investments",
        f"Você tem {brl(value)} investidos (aplicou {brl(invested)}). O resultado é de {'−' if gain < 0 else '+'}{brl(gain)}{pct}.",
        items=[
            {
                "label": r.name,
                "detail": r.institution,
                "value": brl(r.current_value),
                "link": "/investimentos",
            }
            for r in rows[:6]
        ],
        links=[{"label": "Abrir investimentos", "to": "/investimentos"}],
    )


def _salary(db: Session, user: User, period: Period) -> dict[str, Any]:
    rows = list(
        db.scalars(
            select(Income).where(
                Income.user_id == user.id, Income.month.between(period.start, period.end)
            )
        )
    )
    named = [i for i in rows if "salario" in normalize(i.description)]
    fixed = named or [i for i in rows if i.income_type != "variable"]
    if not fixed:
        return _incomes(db, user, period)
    top = max(fixed, key=lambda i: i.amount)
    day = f", no dia {top.day}" if top.day else ""
    return _answer(
        "salary",
        f"{_cap(period.label)}, {top.description} foi de {brl(top.amount)}{day}.",
        items=[
            {
                "label": i.description,
                "detail": f"dia {i.day}" if i.day else None,
                "value": brl(i.amount),
                "link": None,
            }
            for i in sorted(fixed, key=lambda i: -i.amount)[:5]
        ],
    )


def _last_income(db: Session, user: User, current: date) -> dict[str, Any]:
    rows = list(
        db.scalars(
            select(Income)
            .where(Income.user_id == user.id, Income.month <= current)
            .order_by(Income.month.desc(), Income.created_at.desc())
            .limit(40)
        )
    )
    if not rows:
        return _answer(
            "empty",
            "Ainda não há receitas lançadas.",
            links=[{"label": "Lançar receita", "to": "/orcamento"}],
        )

    def when(i: Income) -> date:
        return with_day(i.month, i.day) if i.day else i.month

    today = today_local()
    rows = [i for i in rows if when(i) <= today] or rows
    rows.sort(key=lambda i: (when(i), i.created_at), reverse=True)
    last = rows[0]
    return _answer(
        "last_income",
        f"A última receita foi {last.description}, {brl(last.amount)} em {_short_date(when(last))}.",
        items=[
            {
                "label": i.description,
                "detail": _short_date(when(i)),
                "value": brl(i.amount),
                "link": f"/orcamento/{format_month(i.month)}",
            }
            for i in rows[:3]
        ],
    )


def _average(
    db: Session, user: User, period: Period, subject: Subject | None, current: date
) -> dict[str, Any]:
    if period.single and not period.explicit:
        period = Period(
            add_months(current, -6), add_months(current, -1), "nos últimos 6 meses fechados", False
        )
    rows = _expenses(db, user, period, subject)
    if not rows:
        return _nothing(period, subject)
    totals: dict[date, Decimal] = defaultdict(Decimal)
    for e in rows:
        totals[e.month] += e.amount
    total = sum(totals.values(), Decimal(0))
    about = f" com {subject.label}" if subject else ""
    ranking = sorted(totals.items())
    return _answer(
        "average",
        f"{_cap(period.label)} você gastou em média {brl(total / len(totals))} por mês{about} ({brl(total)} em {_plural(len(totals), 'mês', 'meses')} com gasto).",
        items=[
            {
                "label": _cap(_month_name(m)),
                "detail": None,
                "value": brl(v),
                "link": f"/orcamento/{format_month(m)}",
            }
            for m, v in ranking[-6:]
        ],
    )


def _compare(
    db: Session, user: User, a: Period, b: Period, subject: Subject | None
) -> dict[str, Any]:
    rows_a, rows_b = _expenses(db, user, a, subject), _expenses(db, user, b, subject)
    total_a = sum((e.amount for e in rows_a), Decimal(0))
    total_b = sum((e.amount for e in rows_b), Decimal(0))
    names = _category_names(db, user)

    def by_category(rows: list[Expense]) -> dict[str, Decimal]:
        out: dict[str, Decimal] = defaultdict(Decimal)
        for e in rows:
            out[
                names.get(e.category_id, "Sem categoria") if e.category_id else "Sem categoria"
            ] += e.amount
        return out

    cats_a, cats_b = by_category(rows_a), by_category(rows_b)
    diff = total_a - total_b
    about = f" com {subject.label}" if subject else ""
    if not rows_a and not rows_b:
        return _nothing(a, subject)
    if diff == 0:
        verdict = "o mesmo valor"
    else:
        pct = f" ({abs(diff) / total_b * 100:.0f}%)" if total_b else ""
        verdict = f"{brl(diff)}{pct} {'a mais' if diff > 0 else 'a menos'}"
    changes = sorted(
        (
            (c, cats_a.get(c, Decimal(0)) - cats_b.get(c, Decimal(0)))
            for c in set(cats_a) | set(cats_b)
        ),
        key=lambda kv: -abs(kv[1]),
    )
    items = [
        {
            "label": c,
            "detail": f"{brl(cats_b.get(c, Decimal(0)))} → {brl(cats_a.get(c, Decimal(0)))}",
            "value": ("+" if d > 0 else "−") + brl(d),
            "link": None,
        }
        for c, d in changes[:5]
        if d != 0
    ]
    text = f"{_cap(a.label)} você gastou {brl(total_a)}{about}; {b.label}, {brl(total_b)}. Foram {verdict}."
    if items and subject is None:
        up = next(((c, d) for c, d in changes if d > 0), None)
        if up:
            text += f" O que mais subiu foi {up[0]} (+{brl(up[1])})."
    return _answer(
        "compare",
        text,
        items=[] if subject else items,
        links=[{"label": "Comparar meses nos Insights", "to": "/analises?secao=comparar"}],
    )


def _logged(db: Session, user: User, period: Period) -> dict[str, Any]:
    zone = ZoneInfo(get_settings().timezone)
    first, last = period.day_start, period.day_end
    assert first is not None and last is not None
    since = datetime.combine(first, datetime.min.time(), zone)
    until = datetime.combine(last + timedelta(days=1), datetime.min.time(), zone)
    names = _category_names(db, user)
    expenses = list(
        db.scalars(
            select(Expense)
            .where(
                Expense.user_id == user.id, Expense.created_at >= since, Expense.created_at < until
            )
            .order_by(Expense.created_at.desc())
            .limit(500)
        )
    )
    incomes = list(
        db.scalars(
            select(Income)
            .where(Income.user_id == user.id, Income.created_at >= since, Income.created_at < until)
            .order_by(Income.created_at.desc())
            .limit(20)
        )
    )
    if not expenses and not incomes:
        return _answer(
            "logged",
            f"Nada foi lançado {period.label}.",
            links=[{"label": "Lançar agora", "to": "/orcamento"}],
        )
    parts = []
    if expenses:
        parts.append(
            f"{_plural(len(expenses), 'despesa', 'despesas')} ({brl(sum((e.amount for e in expenses), Decimal(0)))})"
        )
    if incomes:
        parts.append(
            f"{_plural(len(incomes), 'receita', 'receitas')} ({brl(sum((i.amount for i in incomes), Decimal(0)))})"
        )
    items = [_item(e, names) for e in expenses[:6]] + [
        {
            "label": i.description,
            "detail": "receita",
            "value": brl(i.amount),
            "link": f"/orcamento/{format_month(i.month)}",
        }
        for i in incomes[:3]
    ]
    return _answer("logged", f"{_cap(period.label)} você lançou {' e '.join(parts)}.", items=items)


# ---------------------------------------------------------------- pergunta

_SUBSCRIPTION = r"assinatura|streaming|netflix|spotify|prime|disney|hbo|max\b|youtube|icloud|google one|globoplay|deezer|apple|plano|mensalidade|academia|clube"

EXAMPLES = [
    *SUGGESTIONS,
    "Qual foi meu maior lançamento?",
    "Quanto gastei hoje?",
    "Quanto gastei esta semana?",
    "Quanto gasto por mês em média?",
    "Quanto posso gastar hoje?",
    "Tenho alguma conta atrasada?",
    "Qual fatura vence primeiro?",
    "Quantas parcelas faltam?",
    "Quanto devo de financiamento?",
    "Quais assinaturas eu tenho?",
    "Quais são minhas despesas fixas?",
    "Comparar outubro com setembro",
    "Quanto tenho investido?",
    "Quanto falta para minha meta?",
    "Qual meu salário?",
    "Qual foi minha última receita?",
    "Quanto sobrou este mês?",
    "O que lancei hoje?",
]
_NEEDS_SUBJECT = {
    "month_max",
    "last",
    "biggest",
    "sum",
    "average",
    "installments",
    "compare",
    "top",
}
_SPEND = r"\bsaiu\b|\bsairam\b|\bgast|\bpague|\bdespes|\bcompr|\blancament|\bsaid[ao]s?\b|\bdebit"


def _classify(text: str, rest: str, two_periods: bool) -> str | None:
    spends = re.search(_SPEND, text) is not None
    if re.fullmatch(
        r"(muito )?(obrigad[oa]|valeu|vlw|brigad[oa]|show|perfeito|otimo|legal|ok|tchau|ate mais)( mesmo| demais)?",
        text,
    ):
        return "thanks"
    status = re.match(r"como (esta|estao|anda|andam|vai|vao|foi|foram|fiquei|ficou)\b", text)
    if (
        re.match(r"(onde|como|aonde|cade|em que tela|qual tela|tem como)\b", text)
        and not spends
        and not status
    ):
        return "navigate"
    if two_periods or re.search(
        r"\bcompar|\bversus\b|\bvs\b|\b x \b|\bmais\b.*\b(que|do que)\b.*\b(mes|ano|semana)\b", text
    ):
        return "compare"
    if re.search(r"\bqual (o )?mes\b|\bmes (em )?que\b|\bmes mais\b|\bem que mes\b", text) and (
        spends or "mais car" in text
    ):
        return "month_max"
    if re.search(r"\bmeta|\bobjetivo|\bfalta\w* (para|pra)\b", text) and not re.search(
        r"\bparcela", text
    ):
        return "goals"
    if re.search(r"\bparcela", text):
        return "installments"
    if (
        re.search(r"\bfinanciament|\bemprestimo|\bdivida|\bsaldo devedor|\bdevo\b", text)
        and not re.search(r"\bcart[ao]", text)
        and not re.search(r"\bquanto (eu )?(gastei|paguei)\b", text)
    ):
        return "loans"
    if re.search(r"\binvest|\baplicad|\baplicac|\brendimento", text):
        return "investments"
    if re.search(r"\bassinatura|\bfixas?\b|\brecorren|\bmensalidade", text) and not re.search(
        r"\bquanto (eu )?(gastei|paguei)\b", text
    ):
        return "subscriptions" if "assinatura" in text else "recurring"
    if re.search(
        r"\bposso gastar|\bdisponivel|\b(tenho|sobra|resta|restou) (pra|para) gastar|\bainda (tenho|posso)\b|\blivre\b",
        text,
    ):
        return "can_spend"
    if re.search(r"\bultim[oa]s? (receita|salario|entrada|recebimento|renda)", rest):
        return "last_income"
    if re.search(r"\bsalario", text):
        return "salary"
    if re.search(r"\bultim[oa]s? (vez|compra|gasto|despesa|lancamento|pagamento|saida)", rest):
        return "last"
    if re.search(r"\blancei|\bregistrei|\bcadastrei|\blancad[oa]s?\b|\bo que (eu )?lanc", text):
        return "logged"
    if re.search(r"\bmedia\b|\bem media\b|\bmedi[oa] (por|de)\b|\bpor mes\b", text):
        return "average"
    if re.search(r"\bfatura", text) and not re.search(r"\bquanto (eu )?(gastei|paguei)\b", text):
        return "invoices"
    if text.startswith("quando") or re.search(
        r"\bmaior(es)? (gasto|despesa|compra|valor|lancamento|conta|saida|debito)|\bmais (car|alt)[oa]s?\b|\b(gasto|despesa|compra|lancamento)s? mais (car|alt)",
        text,
    ):
        return "biggest"
    if re.search(r"\batrasad|\bvencid|\bem atraso", text):
        return "late"
    if (
        re.search(r"\bvenc|\ba pagar\b|\bpendente|\bpra pagar\b|\bpara pagar\b", text)
        and "fatura" not in text
    ):
        return "due"
    if re.search(r"\bfatura", text):
        return "invoices"
    if re.search(r"\bcarto|\bcartao|\blimite\b", text):
        return "cards"
    if re.search(r"\bmeta|\bobjetivo", text):
        return "goals"
    if re.search(r"\brecebi|\brenda|\breceita|\bganhei|\bentrou|\bentrada", text):
        return "incomes"
    if re.search(
        r"\bsaldo|\bsobr|\bresultado|\bbalanco|\bfechei|\bfaltou|\bfiquei\b|\beconom|\bpoupei|\bguardei",
        text,
    ):
        return "balance"
    if re.search(
        r"\bmais gast|\bgast\w* mais\b|\bonde mais\b|\bcom o que\b|\bo que mais\b|\bpesou\b|\bpesa mais\b|\bem que (eu )?gast|\bcategoria\b.*\bmais\b",
        text,
    ):
        return "top"
    if spends or text.startswith("quanto"):
        return "sum"
    return None


def _suggest_close(text: str) -> list[str]:
    table = {normalize(e).rstrip("?"): e for e in EXAMPLES}
    close = difflib.get_close_matches(text, list(table), n=4, cutoff=0.45)
    words = set(_subject_words(text)) | set(text.split())
    by_word = [e for k, e in table.items() if len(words & set(k.split())) >= 2]
    out = [table[k] for k in close] + [e for e in by_word if e not in [table[k] for k in close]]
    return (out or SUGGESTIONS)[:5]


def answer(
    db: Session,
    user: User,
    question: str,
    today: date | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Responde a pergunta. `context` é o campo `context` da resposta anterior da conversa:
    com ele, "e em setembro?" ou "e com uber?" continuam o assunto."""
    today = today or today_local()
    current = month_of(today, user.month_start_day)
    text = _plain(question[:MAX_QUESTION])
    text = re.sub(r"[?!.,;:]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text or re.fullmatch(
        r"(oi+|ola|opa|ajuda|bom dia|boa tarde|boa noite|o que voce (faz|sabe)|e ai|menu|help)",
        text,
    ):
        return _answer(
            "help",
            "Pergunte sobre os seus lançamentos: gastos por categoria ou lugar, períodos (hoje, semana, mês, ano), vencimentos, "
            "faturas, parcelas, financiamentos, assinaturas, receitas, metas e investimentos. Também mostro onde fica cada coisa no site.",
            suggestions=SUGGESTIONS,
        )

    start_day = user.month_start_day
    period, rest = _parse_period(text, current, today, start_day)
    second: Period | None = None
    if period is not None:
        second, rest2 = _parse_period(rest, current, today, start_day)
        if second is not None:
            rest = rest2
    intent = _classify(text, rest, second is not None)

    # Continuação: "e em setembro?", "e com uber?", "e ontem?".
    previous = context if isinstance(context, dict) else None
    follow = previous is not None and re.match(r"e\b", text) is not None
    subject_text = re.sub(r"^e\b", " ", rest).strip() if follow else rest
    if follow and previous:
        own_subject = bool(_subject_words(subject_text))
        if intent in (None, "sum", "navigate") and previous.get("intent"):
            intent = str(previous["intent"])
        if period is None:
            period = Period.load(previous.get("period"))
        if not own_subject and previous.get("subject"):
            subject_text = str(previous["subject"])[:80]

    found: Subject | None = None
    missing: str | None = None
    if intent is None or intent in _NEEDS_SUBJECT:
        found, missing = _resolve_subject(db, user, subject_text)

    def finish(out: dict[str, Any], key: str | None) -> dict[str, Any]:
        out["context"] = {
            "intent": key,
            "subject": subject_text if found is not None else None,
            "period": period.dump() if period else None,
        }
        return out

    def unknown(term: str) -> dict[str, Any]:
        return _answer(
            "unknown_subject",
            f"Não achei nenhuma categoria ou lançamento com “{term}”.",
            links=[{"label": "Ver categorias", "to": "/ajustes/categorias"}],
            suggestions=_suggest_close(text),
        )

    month = period or _this_month(current)

    if intent == "thanks":
        return finish(
            _answer(
                "thanks", "Por nada! Se quiser, pergunte outra coisa.", suggestions=SUGGESTIONS[:3]
            ),
            None,
        )
    if intent == "navigate":
        place = _navigate(rest)
        if place:
            return finish(place, None)
        return finish(
            _answer(
                "navigate",
                "Não achei esse lugar. Estes são os mais procurados:",
                links=[
                    {"label": label, "to": path}
                    for label, path, _ in PLACES[:1] + PLACES[11:13] + PLACES[18:19]
                ],
                suggestions=["Onde encontro as metas?", "Como exporto meus dados?"],
            ),
            None,
        )
    if intent in ("late", "due"):
        return finish(_due(db, user, today, only_late=intent == "late"), intent)
    if intent == "invoices":
        return finish(_invoices(db, user, today), intent)
    if intent == "cards":
        return finish(_cards(db, user, today), intent)
    if intent == "goals":
        return finish(_goals(db, user, today), intent)
    if intent == "loans":
        return finish(_loans(db, user), intent)
    if intent in ("recurring", "subscriptions"):
        return finish(_recurring(db, user, current, intent == "subscriptions"), intent)
    if intent == "investments":
        return finish(_investments(db, user), intent)
    if intent == "can_spend":
        return finish(_can_spend(db, user, today, current), intent)
    if intent == "salary":
        return finish(_salary(db, user, month), intent)
    if intent == "last_income":
        return finish(_last_income(db, user, current), intent)
    if intent == "incomes":
        return finish(_incomes(db, user, month), intent)
    if intent == "balance":
        return finish(_balance(db, user, month), intent)
    if intent == "logged":
        days = period if period and period.day_start else _days(today, today, "hoje", start_day)
        return finish(_logged(db, user, days), intent)

    if intent in _NEEDS_SUBJECT and missing and intent != "top":
        return finish(unknown(missing), intent)
    if intent == "compare":
        first = period or _this_month(current)
        if second is None:
            if first.day_start and first.day_end:
                span = (first.day_end - first.day_start).days + 1
                second = _days(
                    first.day_start - timedelta(days=span),
                    first.day_start - timedelta(days=1),
                    "no período anterior",
                    start_day,
                )
            elif first.single:
                before = add_months(first.start, -1)
                second = Period(before, before, f"em {_month_name(before)}")
            else:
                months = (
                    (first.end.year - first.start.year) * 12
                    + first.end.month
                    - first.start.month
                    + 1
                )
                second = Period(
                    add_months(first.start, -months),
                    add_months(first.start, -1),
                    "no período anterior",
                )
        if second.start > first.start or (
            second.day_start and first.day_start and second.day_start > first.day_start
        ):
            first, second = second, first  # o mais recente primeiro: "X a mais que antes"
        return finish(_compare(db, user, first, second, found), intent)
    if intent == "month_max":
        return finish(_month_max(db, user, period or _this_year(current), found), intent)
    if intent == "installments":
        return finish(_installments(db, user, current, found), intent)
    if intent == "last":
        return finish(_last(db, user, found), intent)
    if intent == "average":
        return finish(_average(db, user, month, found, current), intent)
    if intent == "biggest":
        default = (
            _this_month(current)
            if re.search(r"\blancament", text) and not text.startswith("quando")
            else _last_year(current)
        )
        return finish(_biggest(db, user, period or default, found), intent)
    if intent == "top":
        if found is not None:
            return finish(_biggest(db, user, month, found), "biggest")
        return finish(_top_categories(db, user, month), intent)
    if intent == "sum":
        return finish(_sum(db, user, month, found), intent)

    # Nada reconhecido: um assunto solto ("uber"), um lugar do site ou sugestões parecidas.
    if found is not None:
        return finish(_sum(db, user, month, found), "sum")
    place = _navigate(text)
    if place:
        return finish(place, None)
    return finish(
        _answer("fallback", "Não entendi essa. Você quis dizer:", suggestions=_suggest_close(text)),
        None,
    )
