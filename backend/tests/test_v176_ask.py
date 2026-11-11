"""v1.7.6: núcleo de linguagem único — vocabulário ampliado, perguntas por partes (medida,
agrupamento, direção, receita ou despesa), correção de digitação e encaminhamento de lançamentos."""

import itertools
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Expense, Income, User
from app.services import ask, lexicon, understand
from app.services.suggest import keyword_category
from tests.test_v17_ask import TODAY, add, data, user  # noqa: F401  (fixtures)


def q(db: Session, question: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    person = db.scalars(select(User)).one()
    return ask.answer(db, person, question, today=TODAY, context=context)


# ---------------------------------------------------------------- vocabulário


def test_vocabulary_has_thousands_of_terms() -> None:
    size = lexicon.size()
    assert size["categories"] >= 6000
    assert size["concepts"] >= 900
    assert size["total"] >= 7000


@pytest.mark.parametrize(
    ("description", "category"),
    [
        ("Supermercado BH", "Alimentação"),
        ("oakberry acai", "Alimentação"),
        ("capsulas nespresso", "Alimentação"),
        ("Uber Black", "Transporte"),
        ("pedagio ecovias", "Transporte"),
        ("troca de pneu", "Transporte"),
        ("conta da sabesp", "Moradia"),
        ("air fryer", "Moradia"),
        ("quinto andar", "Moradia"),
        ("drogaria araujo", "Saúde"),
        ("sessao de terapia", "Saúde"),
        ("mensalidade da academia", "Saúde"),
        ("kumon", "Educação"),
        ("material didatico", "Educação"),
        ("vivo fibra", "Serviços"),
        ("design de sobrancelha", "Serviços"),
        ("das mei", "Serviços"),
        ("chatgpt plus", "Assinaturas"),
        ("game pass ultimate", "Assinaturas"),
        ("ingresso de show", "Lazer"),
        ("airbnb reserva", "Lazer"),
        ("betano", "Lazer"),
        ("shein pedido", "Compras"),
        ("fone bluetooth", "Compras"),
        ("racao golden", "Pets"),
        ("consulta veterinaria", "Pets"),
    ],
)
def test_new_terms_find_the_category(description: str, category: str) -> None:
    assert keyword_category(description) == category


COMMON_WORDS = """
total resumo renda salario saldo cartao hoje semana maio dia casa trabalho geral outros caro barato
maior menor valor media soma categoria lugar cada todo forma visto sobre cara das
""".split()


@pytest.mark.parametrize("word", COMMON_WORDS)
def test_common_words_are_not_categories(word: str) -> None:
    assert keyword_category(word) is None


def test_frontend_copy_of_the_lexicon_is_up_to_date() -> None:
    path = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "lexicon.generated.ts"
    if not path.exists():  # imagem só com o backend
        pytest.skip("frontend ausente")
    from app.cli import lexicon_ts

    assert path.read_text(encoding="utf-8") == lexicon_ts(), (
        "Rode `uv run python -m app.cli lexicon` para atualizar a cópia do site."
    )
    assert json.dumps(lexicon.frontend(), ensure_ascii=False)


# ---------------------------------------------------------------- correção de digitação


@pytest.mark.parametrize(
    ("typed", "fixed"),
    [
        ("qto gastey no mes pasado", "quanto gastei no mes passado"),
        ("quanto gastei com supermecado", "quanto gastei com supermercado"),
        ("qual categoira mais gastei", "qual categoria mais gastei"),
        ("quanto paguei de finaciamento", "quanto paguei de financiamento"),
        ("quais asinaturas eu tenho", "quais assinaturas eu tenho"),
        ("oq vence hj", "o que vence hoje"),
        ("quantas parselas faltam", "quantas parcelas faltam"),
        ("comparar otubro com setenbro", "comparar outubro com setembro"),
    ],
)
def test_typos_are_fixed(typed: str, fixed: str) -> None:
    assert understand.fix_typos(typed) == fixed


@pytest.mark.parametrize(
    "sentence",
    [
        "quanto posso gastar hoje",
        "me fala sobre minhas metas",
        "registrei algo esta semana",
        "qual foi o segundo maior gasto",
        "quanto gastei com a brenda",
        "onde vejo o relatorio anual",
        "como faco para mudar a senha",
        "gastei mais esse mes que no mes passado",
    ],
)
def test_correct_sentences_stay_as_they_are(sentence: str) -> None:
    assert understand.fix_typos(sentence) == sentence


def test_words_of_the_user_are_never_corrected() -> None:
    # "parcelo" pareceria "parcela"; se for uma palavra do próprio usuário, fica.
    assert understand.fix_typos("gasto com parcelo") == "gasto com parcela"
    assert understand.fix_typos("gasto com parcelo", lambda: {"parcelo"}) == "gasto com parcelo"


# ---------------------------------------------------------------- lançamento ou pergunta


@pytest.mark.parametrize(
    ("phrase", "kind"),
    [
        ("gastei 50 no mercado", "amount"),
        ("paguei 200 de luz hoje", "amount"),
        ("mercado 120 pix ontem", "amount"),
        ("uber 23,50 debito", "amount"),
        ("comprei um tenis por 350 no credito", "amount"),
        ("recebi 3000 de salario", "amount"),
        ("+ freelance 600", "amount"),
        ("lancar uber 30", "amount"),
        ("adiciona 45 de ifood", "amount"),
        ("registrar despesa de 80 farmacia", "amount"),
        ("anota ai: padaria 12", "amount"),
        ("pedi ifood 45", "amount"),
        ("almocei 35", "amount"),
        ("netflix 55,90", "amount"),
        ("tv 1990 em 10x credito dia 5", "amount"),
        ("r$ 15 cafe", "amount"),
        ("quero lancar uma despesa", "command"),
        ("adicionar receita", "command"),
        ("nova despesa", "command"),
        ("registrar um gasto", "command"),
        ("quanto gastei no mercado", None),
        ("gastei 50 no mercado?", None),
        ("quanto gastei em 2029", None),
        ("meus gastos com 99", None),
        ("gastos nos ultimos 3 meses", None),
        ("top 5 gastos", None),
        ("5 maiores despesas", None),
        ("media dos ultimos 6 meses", None),
        ("o que lancei hoje", None),
        ("uber", None),
        ("comparar 2029 com 2028", None),
        ("quanto gastei no dia 15", None),
        ("quanto gastei em 12/02", None),
        ("e com uber", None),
        ("como lanco uma despesa", None),
        ("obrigado", None),
    ],
)
def test_entry_or_question(phrase: str, kind: str | None) -> None:
    assert understand.entry_guess(phrase) == kind


def test_bot_does_not_register_and_sends_to_quick_entry(data: TestClient, db: Session) -> None:  # noqa: F811
    before = len(list(db.scalars(select(Expense)))), len(list(db.scalars(select(Income))))
    out = q(db, "Gastei 50 no mercado")
    assert out["intent"] == "entry"
    assert "não registro" in out["answer"]
    assert out["links"] == [
        {"label": "Abrir o Lançamento rápido", "to": "/orcamento?lancar=Gastei%2050%20no%20mercado"}
    ]
    command = q(db, "quero lançar uma despesa")
    assert command["intent"] == "entry" and command["links"][0]["to"] == "/orcamento?lancar="
    after = len(list(db.scalars(select(Expense)))), len(list(db.scalars(select(Income))))
    assert before == after
    api = data.post("/api/ask", json={"question": "mercado 120 pix ontem"}).json()
    assert api["intent"] == "entry" and api["links"][0]["to"].startswith(
        "/orcamento?lancar=mercado"
    )


# ---------------------------------------------------------------- respostas novas


def test_year_with_most_spending(data: TestClient, db: Session) -> None:  # noqa: F811
    for month in ("2029-06", "2029-07"):
        data.get(f"/api/months/{month}")
    add(data, "2029-06", "Viagem", "5000", "Lazer", due_date="2029-06-10", paid=True)
    add(data, "2029-07", "Curso", "900", "Educação", due_date="2029-07-10", paid=True)
    out = q(db, "Qual ano mais gastei?")
    assert out["intent"] == "year_max"
    assert "o ano em que você mais gastou foi 2029: R$ 5.900,00" in out["answer"]
    assert [i["label"] for i in out["items"]] == ["2029", "2030"]
    less = q(db, "em que ano gastei menos")
    assert less["intent"] == "year_min" and "foi 2030: R$ 4.135,00" in less["answer"]
    # Continuação: mesmo ranking, outro assunto.
    follow = q(db, "e com lazer?", out["context"])
    assert follow["intent"] == "year_max" and "com Lazer foi 2029: R$ 5.000,00" in follow["answer"]


def test_day_week_and_weekday_with_most_spending(data: TestClient, db: Session) -> None:  # noqa: F811
    day = q(db, "qual dia gastei mais este mês?")
    assert day["intent"] == "day_max"
    assert "25/03/2030 (segunda-feira): R$ 1.000,00" in day["answer"]
    assert day["links"][0]["to"] == "/orcamento/2030-03"
    least = q(db, "qual dia gastei menos este mês")
    assert least["intent"] == "day_min" and "02/03/2030" in least["answer"]
    week = q(db, "qual semana gastei mais em fevereiro")
    assert week["intent"] == "week_max" and "04/02 a 10/02/2030: R$ 1.000,00" in week["answer"]
    weekday = q(db, "em que dia da semana eu gasto mais?")
    assert weekday["intent"] == "weekday_max" and "nos últimos 3 meses" in weekday["answer"].lower()
    assert weekday["items"]
    assert q(db, "qual o melhor dia de compra do cartão")["intent"] in ("cards", "invoices")


def test_month_ranking_keeps_working_and_gains_the_opposite(data: TestClient, db: Session) -> None:  # noqa: F811
    most = q(db, "Qual mês gastei mais esse ano?")
    assert most["intent"] == "month_max" and "fevereiro de 2030" in most["answer"]
    least = q(db, "qual mês gastei menos este ano")
    assert least["intent"] == "month_min" and "março de 2030: R$ 1.105,00" in least["answer"]
    income = q(db, "qual mês recebi mais?")
    assert (
        income["intent"] == "month_max"
        and "recebeu foi março de 2030: R$ 3.000,00" in income["answer"]
    )


def test_percent_of_income(data: TestClient, db: Session) -> None:  # noqa: F811
    out = q(db, "Quantos % foram gastos dos meus recebimentos?")
    assert out["intent"] == "percent"
    assert "você gastou R$ 1.105,00 de R$ 3.000,00 recebidos: 36,8% das receitas" in out["answer"]
    assert "Sobraram R$ 1.895,00" in out["answer"]
    assert out["items"][2] == {
        "label": "Percentual das receitas",
        "detail": None,
        "value": "36,8%",
        "link": None,
    }
    assert q(db, "qual meu comprometimento de renda")["intent"] == "percent"
    rent = q(db, "quanto por cento da minha renda vai para moradia")
    assert rent["intent"] == "percent" and "Moradia levou 33,3% das suas receitas" in rent["answer"]
    share = q(db, "qual o percentual de gastos com alimentação em fevereiro")
    assert (
        share["intent"] == "percent" and "Alimentação foi 42,2% dos seus gastos" in share["answer"]
    )
    empty = q(db, "quantos % da renda gastei em janeiro")
    assert (
        empty["intent"] == "percent"
        and "Não há receitas lançadas em janeiro de 2030" in empty["answer"]
    )
    # Limite do cartão e metas continuam com as respostas próprias.
    assert q(db, "quantos % do limite do cartão usei")["intent"] == "cards"


def test_count_smallest_per_day_and_list(data: TestClient, db: Session) -> None:  # noqa: F811
    count = q(db, "quantas vezes pedi ifood nos últimos 3 meses")
    assert (
        count["intent"] == "count"
        and "foram 2 lançamentos com “ifood”, somando R$ 140,00" in count["answer"]
    )
    small = q(db, "qual foi meu menor gasto este mês")
    assert small["intent"] == "smallest" and "o menor foi Uber, R$ 45,00" in small["answer"]
    per_day = q(db, "quanto gasto por dia em média")
    assert (
        per_day["intent"] == "per_day" and "R$ 55,25 por dia" in per_day["answer"]
    )  # 1.105 em 20 dias
    listing = q(db, "quanto gastei mês a mês este ano")
    assert listing["intent"] == "month_list"
    assert [i["value"] for i in listing["items"]] == ["R$ 1.300,00", "R$ 1.730,00", "R$ 1.105,00"]
    places = q(db, "em que loja gastei mais este ano")
    assert (
        places["intent"] == "place_max"
        and "onde você mais gastou foi Aluguel: R$ 3.000,00" in places["answer"]
    )


def test_income_and_expense_in_the_same_question(data: TestClient, db: Session) -> None:  # noqa: F811
    out = q(db, "quanto recebi e quanto gastei este mês")
    assert out["intent"] == "balance"
    assert [i["label"] for i in out["items"]] == ["Receitas", "Despesas", "Saldo"]


def test_asks_instead_of_guessing(data: TestClient, db: Session) -> None:  # noqa: F811
    close = q(db, "quanto gastei com alimentacoa")
    assert close["intent"] in ("sum", "unknown_subject")
    unknown = q(db, "quanto gastei com alugue")
    assert unknown["intent"] in ("sum", "unknown_subject")
    vague = q(db, "o que mais xptoabc")
    assert vague["intent"] == "clarify" and len(vague["suggestions"]) == 3
    lost = q(db, "bla bla")
    assert (
        lost["intent"] == "fallback"
        and "Não tenho certeza" in lost["answer"]
        and lost["suggestions"]
    )


# ---------------------------------------------------------------- baterias

REAL = """
qual ano mais gastei => year_max
qual ano gastei mais => year_max
em que ano gastei mais => year_max
qual foi o ano mais caro => year_max
qual o ano que mais gastei => year_max
ano que mais gastei => year_max
qual foi meu pior ano => year_max
qual ano gastei menos => year_min
qual o ano mais barato => year_min
qual dia gastei mais => day_max
qual foi o dia que mais gastei este mês => day_max
em que dia gastei mais em fevereiro => day_max
dia que mais gastei => day_max
que dia eu mais gastei => day_max
qual dia gastei menos => day_min
qual semana gastei mais => week_max
em qual semana gastei mais este mês => week_max
semana em que mais gastei => week_max
qual a semana mais cara => week_max
qual semana gastei menos => week_min
qual dia da semana eu gasto mais => weekday_max
em que dia da semana gasto mais => weekday_max
que dia da semana eu gasto menos => weekday_min
qual mês gastei mais => month_max
qual mês gastei menos => month_min
qual foi o mês mais barato do ano => month_min
meu pior mês => month_max
qual mês recebi mais => month_max
em que mês ganhei menos => month_min
qual ano recebi mais => year_max
em que loja gastei mais => place_max
qual lugar eu mais gasto => place_max
em quais lugares gastei mais este ano => place_max
quantos % foram gastos dos meus recebimentos => percent
quantos por cento da renda eu gastei => percent
quanto por cento da minha renda eu gastei este mês => percent
qual o percentual da renda gasto => percent
qual meu comprometimento => percent
qual meu comprometimento de renda => percent
quanto da minha renda está comprometido => percent
quanto do meu salário eu gasto => percent
qual a porcentagem da receita que gastei => percent
quantos % dos gastos são com alimentação => percent
qual a proporção de moradia nos meus gastos => percent
quantas vezes gastei com uber => count
quantas vezes pedi ifood => count|empty
quantas compras fiz este mês => count
quantos lançamentos fiz em fevereiro => count
quantas despesas tive este ano => count
quantas receitas tive este mês => count
qual foi meu menor gasto => smallest
qual a despesa mais barata do mês => smallest
qual o gasto mais baixo este ano => smallest
quanto gasto por dia => per_day
quanto gasto por dia em média => per_day
qual minha média diária de gastos => per_day
quanto gasto por semana => per_week
qual o gasto semanal médio => per_week
quanto gastei mês a mês => month_list
quanto gastei em cada mês deste ano => month_list
evolução dos meus gastos => month_list
quanto gastei ano a ano => year_list
gastos dia a dia este mês => day_list
quanto recebi e quanto gastei => balance
quanto ganhei e quanto gastei este ano => balance
gastei 50 no mercado => entry
mercado 120 pix ontem => entry
paguei 200 de luz hoje => entry
lançar uber 30 => entry
recebi 3000 de salário => entry
quero registrar um gasto => entry
qual o melhor dia de compra do cartão => cards|invoices
qual dia vence a fatura => cards|invoices
quantas parcelas faltam => installments
quanto falta para minha meta => goals
quanto rende meu investimento => investments
qto gastey esse mes => sum
oq mais gastei esse mes => top_categories
quanto gastei com supermecado no mes pasado => sum|empty|unknown_subject
qual categoira eu mais gasto => top_categories
quais asinaturas eu tenho => recurring
"""

TIME = {"dia": "day", "semana": "week", "mês": "month", "ano": "year"}
ASKS = [
    ("qual {u} gastei {o}", "expense"),
    ("qual {u} {o} gastei", "expense"),
    ("em que {u} gastei {o}", "expense"),
    ("em qual {u} eu gastei {o}", "expense"),
    ("qual foi o {u} em que {o} gastei", "expense"),
    ("{u} em que {o} gastei", "expense"),
    ("{u} que {o} gastei", "expense"),
    ("qual {u} paguei {o} contas", "expense"),
    ("qual {u} recebi {o}", "income"),
    ("em que {u} ganhei {o}", "income"),
    ("qual foi o {u} em que {o} recebi", "income"),
]
ORDERS = {"mais": "max", "menos": "min"}
PERIODS = ["", " este ano", " em 2030", " no ano passado", " nos últimos 6 meses", " em fevereiro"]
SUBJECTS = ["", " com alimentação", " com moradia", " com uber", " em transporte"]


def generated() -> list[tuple[str, set[str]]]:
    """Combinações de pergunta, agrupamento, direção, período e assunto: mais de mil frases."""
    table: list[tuple[str, set[str]]] = []
    for (template, domain), (unit, group), (order, suffix), period, subject in itertools.product(
        ASKS, TIME.items(), ORDERS.items(), PERIODS, SUBJECTS
    ):
        if domain == "income" and (subject or group in ("day", "week")):
            continue
        article = (
            template.replace("qual foi o {u}", "qual foi a {u}") if unit == "semana" else template
        )
        question = article.format(u=unit, o=order) + subject + period
        # Sem lançamento no período, a resposta certa é "não encontrei".
        table.append((question, {f"{group}_{suffix}", "empty"}))
    shares = [
        "quantos % da renda gastei",
        "qual o percentual da renda que gastei",
        "qual meu comprometimento",
    ]
    for start, period in itertools.product(shares, PERIODS):
        table.append((start + period, {"percent"}))
    counts = ["quantas vezes gastei", "quantas compras fiz", "quantos lançamentos fiz"]
    for start, subject, period in itertools.product(counts, SUBJECTS, PERIODS):
        table.append((start + subject + period, {"count", "empty"}))
    for per, subject, period in itertools.product(
        [("quanto gasto por dia", "per_day"), ("quanto gasto por semana", "per_week")],
        SUBJECTS,
        PERIODS,
    ):
        table.append((per[0] + subject + period, {per[1], "empty"}))
    lists = [("quanto gastei mês a mês", "month_list"), ("quanto gastei ano a ano", "year_list")]
    for (start, intent), subject in itertools.product(lists, SUBJECTS):
        table.append((start + subject, {intent, "empty"}))
    for start, subject, period in itertools.product(
        ["qual foi meu menor gasto", "qual a despesa mais barata"], SUBJECTS, PERIODS
    ):
        table.append((start + subject + period, {"smallest", "empty"}))
    return table


def real() -> list[tuple[str, set[str]]]:
    lines = [line.split("=>") for line in REAL.strip().splitlines()]
    return [(question.strip(), set(expected.strip().split("|"))) for question, expected in lines]


def check(db: Session, table: list[tuple[str, set[str]]]) -> list[str]:
    wrong = []
    for question, expected in table:
        got = q(db, question)["intent"]
        if got not in expected:
            wrong.append(f"{question!r}: {got} (esperado {'/'.join(sorted(expected))})")
    return wrong


def test_battery_of_real_questions(data: TestClient, db: Session) -> None:  # noqa: F811
    wrong = check(db, real())
    assert not wrong, "\n".join(wrong)


def test_generated_battery_has_over_a_thousand_questions(data: TestClient, db: Session) -> None:  # noqa: F811
    table = generated()
    assert len(table) >= 1000
    wrong = check(db, table)
    assert not wrong, f"{len(wrong)} de {len(table)}:\n" + "\n".join(wrong[:60])
