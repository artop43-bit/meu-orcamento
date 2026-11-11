"""v1.7.5: Tire sua dúvida, segunda versão — mais formas de perguntar, períodos em dias, temas
novos, continuação da conversa e histórico guardado por 30 dias."""

import uuid
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.types import utcnow
from app.models import AskConversation, User
from app.services import ask, ask_history
from tests.conftest import create_verified_user, login
from tests.test_budget import Outbox
from tests.test_v17_ask import TODAY, add

# Uma pergunta por linha: "pergunta => intenção". As 38 primeiras são as do levantamento que
# motivou a v1.7.5 (20 delas eram respondidas errado na v1.7.0).
BATTERY = """
qual foi meu maior lançamento => biggest
qual meu maior gasto do ano => biggest
qual a maior despesa => biggest
quanto gastei hoje => sum
quanto gastei essa semana => sum
quanto gastei ontem => sum
meus gastos com uber => sum
quanto gastei no total => sum
qual categoria eu mais gasto => top_categories
em que eu gasto mais => top_categories
média de gastos por mês => average
quanto gasto por mês em média => average
quanto economizei este mês => balance
quanto ainda tenho para gastar => can_spend
quanto posso gastar hoje => can_spend
quais contas estão pendentes => due
tenho alguma conta atrasada => due
quanto devo no cartão => cards
qual fatura vence primeiro => cards|invoices
quando vence a fatura do cartão => cards|invoices
quanto falta para minha meta => goals
quanto tenho investido => investments
quanto devo de financiamento => loans
quantas parcelas faltam do celular => installments|unknown_subject
quais são minhas despesas fixas => recurring
quais assinaturas eu tenho => recurring
comparar fevereiro com janeiro => compare
gastei mais esse mês que no mês passado => compare
qual meu salário => salary
de onde vem minha renda => incomes
qual foi minha última receita => last_income
lancei algo hoje => logged
qual foi o gasto mais caro com alimentação em fevereiro => biggest
quanto gastei de alimentação nos últimos 6 meses => sum
como cadastro um cartão => navigate
como faço para mudar a senha => navigate
onde vejo o relatório anual => navigate
obrigado => thanks
maior lançamento do mês => biggest
maiores lançamentos de fevereiro => biggest
qual a maior saída do mês => biggest
qual a compra mais cara => biggest
qual o lançamento mais alto => biggest
maiores despesas com moradia => biggest
quando gastei mais com mercado => biggest
qual foi o maior débito => biggest
quanto gastei anteontem => sum|empty
quanto gastei na semana passada => sum|empty
quanto gastei nos últimos 7 dias => sum|empty
quanto gastei nos últimos 30 dias => sum
quanto gastei no dia 15 => sum
quanto gastei em 12/02 => sum
quanto gastei em 12/02/2030 => sum
gastos de hoje => sum
despesas desta semana => sum
quanto paguei de aluguel => sum
quanto gastei com transporte este ano => sum
quanto gastei em janeiro => sum
quanto gastei em janeiro de 2030 => sum
total de gastos do ano => sum
quanto saiu este mês => sum|balance|fallback
gastos com ifood no mês passado => sum
quanto foi de mercado em fevereiro => sum
uber => sum
alimentação => sum
quanto gastei com xyzabc123 => unknown_subject
onde mais gastei => top_categories
com o que gastei mais em fevereiro => top_categories
o que mais pesou no mês => top_categories
qual categoria pesa mais => top_categories
em que gastei mais este ano => top_categories
qual mês gastei mais => month_max
em que mês gastei mais com mercado => month_max
qual o mês mais caro do ano => month_max
média mensal de gastos => average
quanto gasto em média com alimentação => average
gasto médio por mês => average
média de gastos com mercado nos últimos 3 meses => average
quanto sobrou este mês => balance
quanto sobrou no mês passado => balance
como fiquei em fevereiro => balance
qual meu saldo => balance
qual o resultado do mês => balance
quanto guardei este mês => balance
quanto poupei este ano => balance
fechei no positivo => balance
quanto recebi este mês => incomes
quanto entrou em março => incomes
minhas receitas do ano => incomes
quanto ganhei este ano => incomes
quanto entrou de salário => salary
qual o valor do meu salário => salary
quando cai meu salário => salary
última entrada => last_income
último recebimento => last_income
qual foi minha última compra => last
último gasto com ifood => last
quando foi a última vez que paguei uber => last
último lançamento => last
o que vence nos próximos dias => due
contas a pagar => due
o que tenho para pagar => due
o que está pendente => due
contas atrasadas => due
o que está vencido => due
tem conta em atraso => due
qual o limite do meu cartão => cards
quanto usei do cartão => cards
quanto tenho disponível no cartão => can_spend|cards
valor da fatura => cards|invoices
quanto está a fatura do nubank => cards|invoices
quando fecha a fatura => cards|invoices
como estão minhas metas => goals
quanto falta para a viagem => goals|unknown_subject|sum|fallback
quando termino minha meta => goals|biggest
meus objetivos => goals
quanto tenho aplicado => investments
como estão meus investimentos => investments
qual o rendimento dos meus investimentos => investments
quanto devo => loans|cards|fallback|sum|empty
saldo devedor do financiamento => loans
quanto falta pagar do empréstimo => loans
minhas dívidas => loans
quantas parcelas faltam => installments
parcelas em aberto => installments
quando acabam as parcelas => installments
minhas assinaturas => recurring
quanto pago de assinaturas por mês => recurring|sum|average
contas fixas => recurring
despesas recorrentes => recurring
quanto pago de mensalidade => recurring|sum|unknown_subject|empty
comparar este mês com o mês passado => compare
março x fevereiro => compare
fevereiro versus janeiro => compare
gastei mais ou menos que no mês passado => compare
compare alimentação de fevereiro com janeiro => compare
quanto posso gastar => can_spend
tenho saldo livre => can_spend|balance
quanto sobra para gastar hoje => can_spend
qual meu disponível => can_spend
o que lancei hoje => logged
o que foi lançado ontem => logged
registrei algo esta semana => logged
onde encontro as recorrências => navigate
onde fica a calculadora de juros => navigate
como exporto meus dados => navigate
onde mudo a cor do tema => navigate
onde vejo meus investimentos => navigate
cadê o calendário => navigate
como importo um extrato => navigate
onde altero meu perfil => navigate
como instalo o app => navigate
onde vejo as novidades => navigate
como crio uma meta => navigate
onde cadastro uma categoria => navigate
como divido uma conta => navigate
onde peço ajuda => navigate
oi => help
olá => help
ajuda => help
bom dia => help
valeu => thanks
muito obrigado => thanks
ok => thanks
blá blá blá => fallback
asdfgh => fallback
"""


def cases() -> list[tuple[str, set[str]]]:
    out = []
    for line in BATTERY.strip().splitlines():
        question, expected = line.split(" => ")
        out.append((question, set(expected.split("|"))))
    return out


@pytest.fixture
def user(client: TestClient, outbox: Outbox) -> TestClient:
    create_verified_user(client, outbox)
    login(client)
    return client


@pytest.fixture
def data(user: TestClient) -> TestClient:
    for month in ("2030-01", "2030-02", "2030-03"):
        user.get(f"/api/months/{month}")
    add(user, "2030-01", "Mercado Extra", "300", "Alimentação", due_date="2030-01-10", paid=True)
    add(user, "2030-01", "Aluguel", "1000", "Moradia", due_date="2030-01-05", paid=True)
    add(user, "2030-02", "Mercado Extra", "650", "Alimentação", due_date="2030-02-12", paid=True)
    add(user, "2030-02", "Aluguel", "1000", "Moradia", due_date="2030-02-05", paid=True)
    add(user, "2030-02", "iFood pizza", "80", "Alimentação", due_date="2030-02-20", paid=True)
    add(user, "2030-03", "Aluguel", "1000", "Moradia", due_date="2030-03-25")
    add(user, "2030-03", "Uber", "45", "Transporte", due_date="2030-03-19", paid=True)
    add(user, "2030-03", "iFood lanche", "60", "Alimentação", due_date="2030-03-20", paid=True)
    add(user, "2030-03", "Padaria", "12", "Alimentação", due_date="2030-03-15", paid=True)
    user.post(
        "/api/months/2030-03/incomes", json={"description": "Salário", "amount": "3000", "day": 5}
    )
    user.post("/api/months/2030-03/incomes", json={"description": "Freela", "amount": "400"})
    return user


def q(db: Session, question: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    account = db.scalars(select(User)).one()
    return ask.answer(db, account, question, today=TODAY, context=context)


def test_battery_of_real_questions(data: TestClient, db: Session) -> None:
    table = cases()
    assert len(table) >= 150
    wrong = []
    for question, expected in table:
        got = q(db, question)["intent"]
        if got not in expected:
            wrong.append(f"{question!r}: {got} (esperado {'/'.join(sorted(expected))})")
    assert not wrong, "\n".join(wrong)


def test_short_periods_filter_by_day(data: TestClient, db: Session) -> None:
    # Hoje é 20/03/2030 (quarta): só o iFood lanche é de hoje; o Uber é de ontem.
    assert "R$ 60,00" in q(db, "quanto gastei hoje")["answer"]
    yesterday = q(db, "quanto gastei ontem")
    assert "R$ 45,00" in yesterday["answer"] and yesterday["answer"].startswith("Ontem")
    week = q(db, "quanto gastei esta semana")  # segunda 18 a quarta 20
    assert "R$ 105,00" in week["answer"]
    assert "R$ 12,00" in q(db, "quanto gastei no dia 15")["answer"]
    assert "R$ 650,00" in q(db, "quanto gastei em 12/02")["answer"]
    assert "R$ 117,00" in q(db, "quanto gastei nos últimos 7 dias")["answer"]


def test_biggest_entry_of_the_month_and_money_casing(data: TestClient, db: Session) -> None:
    out = q(db, "Qual foi meu maior lançamento")
    assert out["intent"] == "biggest" and "Aluguel" in out["answer"]
    assert out["items"][0]["value"] == "R$ 1.000,00"
    # "R$" nunca vira "r$" no começo ou no meio da frase.
    for question in ("contas a pagar", "contas atrasadas", "o que lancei hoje", "qual meu saldo"):
        assert "r$" not in q(db, question)["answer"]


def test_specific_answers(data: TestClient, db: Session) -> None:
    late = q(db, "tenho alguma conta atrasada")
    assert late["answer"].startswith("Nenhuma conta atrasada")
    due = q(db, "contas a pagar")
    assert [i["label"] for i in due["items"]] == ["Aluguel"]
    salary = q(db, "qual meu salário")
    assert "R$ 3.000,00" in salary["answer"] and "dia 5" in salary["answer"]
    average = q(db, "quanto gasto por mês em média")
    assert "R$ 1.515,00" in average["answer"]  # janeiro 1.300 + fevereiro 1.730 em 2 meses
    compare = q(db, "comparar fevereiro com janeiro")
    assert "R$ 430,00" in compare["answer"] and "a mais" in compare["answer"]
    fixed = q(db, "quanto sobrou este mês")
    assert "Sobraram R$ 2.283,00" in fixed["answer"]


def test_follow_up_keeps_subject_or_period(data: TestClient, db: Session) -> None:
    first = q(db, "quanto gastei com mercado em fevereiro")
    assert "R$ 650,00" in first["answer"]
    january = q(db, "e em janeiro?", context=first["context"])
    assert january["intent"] == "sum" and "R$ 300,00" in january["answer"]
    assert "mercado" in january["answer"]
    ifood = q(db, "e com ifood?", context=january["context"])
    assert ifood["intent"] in ("sum", "empty") and "janeiro de 2030" in ifood["answer"]
    biggest = q(db, "qual foi meu maior lançamento")
    before = q(db, "e em fevereiro?", context=biggest["context"])
    assert before["intent"] == "biggest" and "fevereiro de 2030" in before["answer"]
    # Sem contexto, "e em janeiro?" não inventa assunto.
    assert q(db, "e em janeiro?")["intent"] in ("fallback", "sum", "empty")


def test_unknown_question_suggests_similar_ones(data: TestClient, db: Session) -> None:
    out = q(db, "quanto posso gatar oje")
    assert out["suggestions"] and any("posso gastar" in s.lower() for s in out["suggestions"])


# ---------------------------------------------------------------- histórico


def test_history_is_saved_listed_and_continued(data: TestClient) -> None:
    first = data.post(
        "/api/ask", json={"question": "quanto gastei com mercado em fevereiro de 2030"}
    )
    conversation = first.json()["conversation_id"]
    assert conversation
    # A continuação usa o contexto guardado no servidor (o navegador só manda o id).
    second = data.post(
        "/api/ask", json={"question": "e em janeiro de 2030?", "conversation_id": conversation}
    ).json()
    assert second["conversation_id"] == conversation and "R$ 300,00" in second["answer"]
    other = data.post("/api/ask", json={"question": "contas a pagar"}).json()["conversation_id"]
    listing = data.get("/api/ask/conversations").json()
    assert [c["id"] for c in listing] == [other, conversation]
    assert listing[1]["title"] == "quanto gastei com mercado em fevereiro de 2030"
    messages = data.get(f"/api/ask/conversations/{conversation}").json()
    assert [m["question"] for m in messages] == [
        "quanto gastei com mercado em fevereiro de 2030",
        "e em janeiro de 2030?",
    ]
    assert messages[0]["answer"]["intent"] == "sum"
    # Vai no backup (portabilidade).
    backup = data.get("/api/export/backup").json()
    assert len(backup["ask_conversations"]) == 2
    assert data.delete(f"/api/ask/conversations/{other}").status_code == 204
    assert len(data.get("/api/ask/conversations").json()) == 1
    assert data.delete("/api/ask/conversations").status_code == 204
    assert data.get("/api/ask/conversations").json() == []


def test_history_expires_after_30_days(data: TestClient, db: Session) -> None:
    old = data.post("/api/ask", json={"question": "contas a pagar"}).json()["conversation_id"]
    new = data.post("/api/ask", json={"question": "qual meu saldo"}).json()["conversation_id"]
    db.execute(
        update(AskConversation)
        .where(AskConversation.id == uuid.UUID(old))
        .values(updated_at=utcnow() - timedelta(days=31))
    )
    db.commit()
    assert [c["id"] for c in data.get("/api/ask/conversations").json()] == [new]
    assert data.get(f"/api/ask/conversations/{old}").status_code == 404
    # A limpeza diária (app.cli cleanup) também apaga.
    db.execute(update(AskConversation).values(updated_at=utcnow() - timedelta(days=40)))
    db.commit()
    assert ask_history.purge(db) == 1


def test_history_can_be_turned_off(data: TestClient) -> None:
    assert data.get("/api/auth/me").json()["ask_history"] is True
    data.post("/api/ask", json={"question": "contas a pagar"})
    assert data.patch("/api/ask/settings", json={"history": False}).json() == {"history": False}
    # Desligar apaga o que estava guardado e nada novo é salvo.
    assert data.get("/api/ask/conversations").json() == []
    out = data.post(
        "/api/ask", json={"question": "quanto gastei com mercado em fevereiro de 2030"}
    ).json()
    assert out["conversation_id"] is None and data.get("/api/ask/conversations").json() == []
    # A continuação segue funcionando com o contexto devolvido pelo navegador.
    again = data.post(
        "/api/ask", json={"question": "e em janeiro de 2030?", "context": out["context"]}
    ).json()
    assert "R$ 300,00" in again["answer"]
    assert data.patch("/api/ask/settings", json={"history": True}).json() == {"history": True}


def test_conversations_are_private(data: TestClient, client: TestClient, outbox: Outbox) -> None:
    mine = data.post("/api/ask", json={"question": "contas a pagar"}).json()["conversation_id"]
    data.post("/api/auth/logout")
    create_verified_user(client, outbox, "bia@example.com")
    login(client, "bia@example.com")
    assert client.get("/api/ask/conversations").json() == []
    assert client.get(f"/api/ask/conversations/{mine}").status_code == 404
    assert client.delete(f"/api/ask/conversations/{mine}").status_code == 404
    stolen = client.post("/api/ask", json={"question": "e agora?", "conversation_id": mine})
    assert stolen.status_code == 404


def test_today_is_a_weekday_helper() -> None:
    assert TODAY == date(2030, 3, 20) and TODAY.weekday() == 2
