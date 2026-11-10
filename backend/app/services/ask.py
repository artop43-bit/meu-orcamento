"""Tire sua dúvida (v1.7): perguntas sobre os próprios dados, respondidas por regras.

Tudo roda aqui no servidor, sem serviço externo: a pergunta é lida por palavras-chave
(período, assunto e o que se quer saber) e a resposta sai das tabelas do próprio usuário.
A pergunta não é guardada.

Exemplos: "o que mais gastei esse mês?", "qual mês gastei mais esse ano?",
"quando gastei mais em mercado?", "quanto gastei com ifood em outubro?",
"onde encontro as recorrências?".
"""

import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.months import add_months, format_month, month_of, today_local
from app.models import Category, Expense, Goal, Income, User
from app.services import cards
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


def _plural(count: int, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


# ---------------------------------------------------------------- período

_NUMBERS = {"dois": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "doze": 12}
_MONTHS = {normalize(name): i + 1 for i, name in enumerate(MONTH_NAMES)}
_THIS = r"(?:este|esse|neste|nesse|deste|desse|nesta|nessa|o|no|do)"


@dataclass
class Period:
    start: date
    end: date
    label: str  # "em novembro de 2026", "neste ano"...
    explicit: bool = True

    @property
    def single(self) -> bool:
        return self.start == self.end


def _parse_period(text: str, current: date) -> tuple[Period | None, str]:
    """Acha o período na pergunta e devolve o texto sem ele."""

    def cut(match: re.Match[str]) -> str:
        return (text[: match.start()] + " " + text[match.end() :]).strip()

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
    if m := re.search(rf"\b{_THIS}\s+mes\b|\bmes atual\b|\bhoje\b", text):
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
    query = select(Expense).where(
        Expense.user_id == user.id, Expense.month.between(period.start, period.end)
    )
    if subject is not None and subject.condition() is not None:
        query = query.where(subject.condition())
    rows = list(db.scalars(query))
    return [e for e in rows if _matches(e, subject)]


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
        f"{period.label.capitalize()}, o que mais pesou foi {first}: {brl(value)} ({share} de {brl(total)}). "
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
    answer = f"{period.label.capitalize()}, o mês em que você mais gastou{about} foi {_month_name(month)}: {brl(value)}."
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
    answer = f"{period.label.capitalize()} você gastou {brl(total)}{about}, em {_plural(len(rows), 'lançamento', 'lançamentos')}."
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
        f"{period.label.capitalize()} entraram {brl(total)} em {_plural(len(rows), 'receita', 'receitas')}.",
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
        f"{period.label.capitalize()}: receitas {brl(earned)}, despesas {brl(spent)}. {word.capitalize()} {brl(result)}.",
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


def _due(db: Session, user: User, today: date) -> dict[str, Any]:
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
    soon = [e for e in rows if e.due_date and e.due_date >= today]
    if not rows:
        return _answer("due", "Nada vencendo nos próximos 10 dias e nenhuma conta atrasada. 👍")
    parts = []
    if soon:
        parts.append(
            f"{_plural(len(soon), 'conta vence', 'contas vencem')} nos próximos 10 dias ({brl(sum((e.amount for e in soon), Decimal(0)))})"
        )
    if late:
        parts.append(
            f"{_plural(len(late), 'está atrasada', 'estão atrasadas')} ({brl(sum((e.amount for e in late), Decimal(0)))})"
        )
    names = _category_names(db, user)
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
        " e ".join(parts).capitalize() + ".",
        items=items,
        links=[{"label": "Abrir o calendário", "to": "/calendario"}],
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


def _goals(db: Session, user: User) -> dict[str, Any]:
    goals = list(
        db.scalars(
            select(Goal)
            .where(Goal.user_id == user.id)
            .order_by(Goal.is_main.desc(), Goal.created_at)
        )
    )
    if not goals:
        return _answer(
            "goals",
            "Você ainda não tem metas.",
            links=[{"label": "Criar uma meta", "to": "/metas"}],
        )
    items = []
    for g in goals[:TOP]:
        pct = int(g.current_amount / g.target_amount * 100) if g.target_amount else 0
        detail = f"{pct}% de {brl(g.target_amount)}"
        if g.target_date:
            detail += f" · até {_short_date(g.target_date)}"
        items.append(
            {"label": g.name, "detail": detail, "value": brl(g.current_amount), "link": "/metas"}
        )
    done = sum(1 for g in goals if g.target_amount and g.current_amount >= g.target_amount)
    answer = f"Você tem {_plural(len(goals), 'meta', 'metas')}"
    answer += f", {_plural(done, 'concluída', 'concluídas')}." if done else "."
    return _answer("goals", answer, items=items, links=[{"label": "Abrir metas", "to": "/metas"}])


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


# ---------------------------------------------------------------- pergunta


def answer(db: Session, user: User, question: str, today: date | None = None) -> dict[str, Any]:
    today = today or today_local()
    current = month_of(today, user.month_start_day)
    text = normalize(question[:MAX_QUESTION]).replace("?", " ").replace("!", " ")
    text = re.sub(r"\s+", " ", text).strip()
    if not text or re.fullmatch(
        r"(oi|ola|ajuda|bom dia|boa tarde|boa noite|o que voce faz|e ai)", text
    ):
        return _answer(
            "help",
            "Pergunte sobre os seus lançamentos: gastos por categoria ou lugar, meses, vencimentos, cartões, receitas e metas. "
            "Também mostro onde fica cada coisa no site.",
            suggestions=SUGGESTIONS,
        )

    period, rest = _parse_period(text, current)
    spends = re.search(r"\bgast|\bpague|\bdespes|\bcompr", text) is not None

    def subject() -> tuple[Subject | None, str | None]:
        return _resolve_subject(db, user, rest)

    def unknown(term: str) -> dict[str, Any]:
        return _answer(
            "unknown_subject",
            f"Não achei nenhuma categoria ou lançamento com “{term}”.",
            links=[{"label": "Ver categorias", "to": "/ajustes/categorias"}],
            suggestions=["O que mais gastei este mês?"],
        )

    # "Onde encontro…" / "Como faço…" (antes de "onde mais gastei", que é sobre gastos).
    status = re.match(r"como (esta|estao|anda|andam|vai|vao|foi|foram|fiquei|ficou)\b", text)
    if (
        re.match(r"(onde|como|aonde|cade|em que tela|qual tela|tem como)\b", text)
        and not spends
        and not status
    ):
        found = _navigate(rest)
        if found:
            return found
        return _answer(
            "navigate",
            "Não achei esse lugar. Estes são os mais procurados:",
            links=[
                {"label": label, "to": path}
                for label, path, _ in PLACES[:1] + PLACES[11:13] + PLACES[18:19]
            ],
            suggestions=["Onde encontro as metas?", "Como exporto meus dados?"],
        )

    if re.search(r"\bqual (o )?mes\b|\bmes (em )?que\b|\bmes mais\b|\bem que mes\b", text) and (
        spends or "mais car" in text
    ):
        found, missing = subject()
        if missing:
            return unknown(missing)
        return _month_max(db, user, period or _this_year(current), found)

    if re.search(r"\bultim[oa]s? (vez|compra|gasto|despesa|lancamento|pagamento)", rest):
        found, missing = subject()
        if missing:
            return unknown(missing)
        return _last(db, user, found)

    if text.startswith("quando") or re.search(
        r"\bmaior(es)? (gasto|despesa|compra|valor)|\bmais (car|alt)[oa]s?\b", text
    ):
        found, missing = subject()
        if missing:
            return unknown(missing)
        return _biggest(db, user, period or _last_year(current), found)

    if re.search(r"\bvenc|\ba pagar\b|\bpendente|\batrasad|\bpra pagar\b|\bpara pagar\b", text):
        return _due(db, user, today)
    if re.search(r"\bcarto|\bcartao|\bfatura|\blimite\b", text):
        return _cards(db, user, today)
    if re.search(r"\bmeta|\bobjetivo", text):
        return _goals(db, user)
    if re.search(r"\brecebi|\brenda|\breceita|\bsalario|\bganhei|\bentrou|\bentrada", text):
        return _incomes(db, user, period or _this_month(current))
    if re.search(r"\bsaldo|\bsobr|\bresultado|\bbalanco|\bfechei|\bfaltou|\bfiquei\b", text):
        return _balance(db, user, period or _this_month(current))

    found, missing = subject()
    if re.search(
        r"\bmais gast|\bgast\w* mais\b|\bonde mais\b|\bcom o que\b|\bo que mais\b|\bpesou\b|\bpesa mais\b",
        text,
    ):
        if found is not None:
            return _biggest(db, user, period or _this_month(current), found)
        return _top_categories(db, user, period or _this_month(current))
    if missing and (spends or text.startswith("quanto")):
        return unknown(missing)
    if spends or text.startswith("quanto") or found is not None:
        return _sum(db, user, period or _this_month(current), found)

    found_place = _navigate(text)
    if found_place:
        return found_place
    return _answer(
        "fallback",
        "Não entendi essa. Tente perguntar assim:",
        suggestions=SUGGESTIONS[:5],
    )
