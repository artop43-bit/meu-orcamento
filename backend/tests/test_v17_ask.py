"""v1.7: Tire sua dúvida — perguntas respondidas por regras, com os dados do próprio usuário."""

from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User
from app.services import ask
from tests.conftest import create_verified_user, login
from tests.test_analysis import category_id
from tests.test_budget import Outbox

TODAY = date(2030, 3, 20)  # mês atual: março de 2030


@pytest.fixture
def user(client: TestClient, outbox: Outbox) -> TestClient:
    create_verified_user(client, outbox)
    login(client)
    return client


def add(
    client: TestClient,
    month: str,
    description: str,
    amount: str,
    category: str | None,
    **extra: Any,
) -> None:
    payload: dict[str, Any] = {"description": description, "amount": amount, **extra}
    if category:
        payload["category_id"] = category_id(client, category)
    response = client.post(f"/api/months/{month}/expenses", json=payload)
    assert response.status_code == 201, response.text


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
    add(user, "2030-03", "Uber", "45", "Transporte", due_date="2030-03-02", paid=True)
    add(user, "2030-03", "iFood lanche", "60", "Alimentação", due_date="2030-03-15")
    user.post("/api/months/2030-03/incomes", json={"description": "Salário", "amount": "3000"})
    return user


def q(db: Session, question: str) -> dict[str, Any]:
    user = db.scalars(select(User)).one()
    out = ask.answer(db, user, question, today=TODAY)
    # A resposta também passa pela API (mesmo formato).
    return out


def test_top_categories_this_month(data: TestClient, db: Session) -> None:
    out = q(db, "O que mais gastei esse mês?")
    assert out["intent"] == "top_categories"
    assert "Moradia" in out["answer"] and "R$ 1.000,00" in out["answer"]
    assert [i["label"] for i in out["items"]] == ["Moradia", "Alimentação", "Transporte"]


def test_month_with_most_spending_this_year(data: TestClient, db: Session) -> None:
    out = q(db, "Qual mês gastei mais esse ano?")
    assert out["intent"] == "month_max"
    assert "fevereiro de 2030" in out["answer"] and "R$ 1.730,00" in out["answer"]
    assert out["links"][0]["to"] == "/orcamento/2030-02"


def test_when_did_i_spend_most_in_a_category(data: TestClient, db: Session) -> None:
    out = q(db, "Quando gastei mais em alimentação?")
    assert out["intent"] == "biggest"
    first = out["items"][0]
    assert first["label"] == "Mercado Extra" and first["value"] == "R$ 650,00"
    assert first["detail"].startswith("12/02/2030")
    assert first["link"] == "/orcamento/2030-02"


def test_category_found_by_keyword_like_quick_entry(data: TestClient, db: Session) -> None:
    # "comida" não é nome de categoria nem aparece nas descrições: vem do dicionário.
    out = q(db, "quando gastei mais com comida")
    assert out["intent"] == "biggest" and "Alimentação" in out["answer"]


def test_sum_by_place_and_period(data: TestClient, db: Session) -> None:
    out = q(db, "Quanto gastei com ifood em fevereiro?")
    assert out["intent"] == "sum"
    assert "R$ 80,00" in out["answer"] and "fevereiro de 2030" in out["answer"]
    out = q(db, "quanto gastei com ifood nos últimos 3 meses")
    assert "R$ 140,00" in out["answer"]


def test_sum_last_month(data: TestClient, db: Session) -> None:
    out = q(db, "quanto gastei no mês passado?")
    assert "R$ 1.730,00" in out["answer"]


def test_last_purchase(data: TestClient, db: Session) -> None:
    out = q(db, "qual foi minha última compra no ifood?")
    assert out["intent"] == "last" and "iFood lanche" in out["answer"]


def test_incomes_balance_and_due(data: TestClient, db: Session) -> None:
    assert "R$ 3.000,00" in q(db, "quanto recebi esse mês?")["answer"]
    balance = q(db, "quanto sobrou esse mês?")
    assert balance["intent"] == "balance" and "Sobraram R$ 1.895,00" in balance["answer"]
    due = q(db, "o que vence nos próximos dias?")
    assert due["intent"] == "due"
    labels = [i["label"] for i in due["items"]]
    # iFood (15/03) está atrasado; Aluguel vence em 25/03; o Uber já foi pago.
    assert labels == ["iFood lanche", "Aluguel"]
    assert due["items"][0]["detail"].startswith("atrasada")


def test_goals_and_cards_without_data(data: TestClient, db: Session) -> None:
    assert q(db, "como estão minhas metas?")["intent"] == "goals"
    assert q(db, "quanto tenho na fatura do cartão?")["intent"] == "cards"


def test_where_can_i_find(data: TestClient, db: Session) -> None:
    out = q(db, "Onde encontro as recorrências?")
    assert out["intent"] == "navigate"
    assert out["links"][0]["to"] == "/ajustes/recorrencias"
    assert q(db, "como exporto meus dados?")["links"][0]["to"] == "/ajustes/dados"
    assert (
        q(db, "onde fica a calculadora de juros")["links"][0]["to"]
        == "/analises?secao=calculadoras"
    )
    # "Onde mais gastei" é sobre gastos, não sobre telas.
    assert q(db, "onde mais gastei este mês?")["intent"] == "top_categories"


def test_unknown_subject_and_fallback(data: TestClient, db: Session) -> None:
    out = q(db, "quanto gastei com xptoabc?")
    assert out["intent"] == "unknown_subject" and "xptoabc" in out["answer"]
    assert q(db, "bla bla")["intent"] == "fallback"
    assert q(db, "oi")["suggestions"]


def test_only_own_data_and_api(data: TestClient, client: TestClient, outbox: Outbox) -> None:
    out = data.post("/api/ask", json={"question": "o que mais gastei esse ano?"})
    assert out.status_code == 200
    body = out.json()
    assert set(body) == {"intent", "answer", "items", "links", "suggestions"}
    assert data.post("/api/ask", json={"question": ""}).status_code == 422
    # Outra pessoa não vê nada dos lançamentos acima.
    data.post("/api/auth/logout")
    create_verified_user(client, outbox, "bia@example.com")
    login(client, "bia@example.com")
    other = client.post("/api/ask", json={"question": "o que mais gastei esse ano?"}).json()
    assert "Moradia" not in other["answer"] and other["intent"] == "empty"


@pytest.mark.parametrize(
    ("question", "intent"),
    [
        ("Com o que eu mais gastei em fevereiro?", "top_categories"),
        ("em que mês gastei mais com aluguel", "month_max"),
        ("qual o mês mais caro do ano", "month_max"),
        ("maiores gastos do mês", "biggest"),
        ("quais foram as despesas mais caras em 2030", "biggest"),
        ("quando foi a última vez que paguei uber", "last"),
        ("quanto gastei de transporte", "sum"),
        ("gastos com moradia este ano", "sum"),
        ("contas atrasadas", "due"),
        ("qual o limite do meu cartão", "cards"),
        ("quanto entrou de salário", "incomes"),
        ("como fiquei no mês passado", "balance"),
        ("onde mudo a cor do tema?", "navigate"),
        ("onde vejo meus investimentos", "navigate"),
        ("cadê o calendário", "navigate"),
    ],
)
def test_many_ways_to_ask(data: TestClient, db: Session, question: str, intent: str) -> None:
    assert q(db, question)["intent"] == intent
