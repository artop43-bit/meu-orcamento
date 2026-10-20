from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.email import OutgoingEmail
from app.models import CreditCard
from app.services import budget as budget_service
from app.services import cards, daily
from tests.conftest import create_verified_user, login

MONTH = "2030-01"


@pytest.fixture
def user(client: TestClient, outbox: list[OutgoingEmail]) -> TestClient:
    create_verified_user(client, outbox)
    login(client)
    return client


@pytest.fixture(autouse=True)
def fixed_current_month(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(budget_service, "current_month", lambda *_: date(2030, 1, 1))


def category_id(client: TestClient, name: str) -> str:
    return next(c["id"] for c in client.get("/api/categories").json() if c["name"] == name)


def add_expense(client: TestClient, month: str = MONTH, **data: Any) -> list[dict[str, Any]]:
    payload = {"description": "Conta", "amount": "100.00", **data}
    response = client.post(f"/api/months/{month}/expenses", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def new_card(client: TestClient, **data: Any) -> dict[str, Any]:
    payload = {"name": "Nubank", "limit_amount": "3000.00", "closing_day": 3, "due_day": 10, **data}
    response = client.post("/api/cards", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------- regra da fatura


def test_invoice_dates_rules() -> None:
    card = CreditCard(closing_day=3, due_day=10)
    # Antes do fechamento: fatura que fecha dia 3 do mês e vence dia 10.
    assert cards.invoice_dates(card, date(2030, 1, 2)) == (date(2030, 1, 3), date(2030, 1, 10))
    # No dia do fechamento ou depois: vai para a próxima.
    assert cards.invoice_dates(card, date(2030, 1, 3)) == (date(2030, 2, 3), date(2030, 2, 10))
    # Vencimento antes do fechamento no calendário: vence no mês seguinte ao fechamento.
    late = CreditCard(closing_day=25, due_day=5)
    assert cards.invoice_dates(late, date(2030, 1, 20)) == (date(2030, 1, 25), date(2030, 2, 5))
    # Fevereiro sem dia 30: usa o último dia.
    end = CreditCard(closing_day=30, due_day=8)
    assert cards.invoice_dates(end, date(2030, 2, 10))[0] == date(2030, 2, 28)


def test_card_purchase_goes_to_invoice_month(user: TestClient) -> None:
    card = new_card(user)
    [expense] = add_expense(
        user, description="Tênis", amount="300.00", card_id=card["id"], purchase_date="2030-01-05"
    )
    assert expense["month"] == "2030-02"
    assert expense["due_date"] == "2030-02-10"
    assert expense["purchase_date"] == "2030-01-05"
    assert expense["payment_method"] == "credit"
    assert expense["card_id"] == card["id"]


def test_card_installments_follow_invoices(user: TestClient) -> None:
    card = new_card(user)
    parcels = add_expense(
        user,
        description="Geladeira",
        amount="3000.00",
        installments=3,
        amount_mode="total",
        card_id=card["id"],
        purchase_date="2030-01-02",
    )
    assert [(p["month"], p["amount"]) for p in parcels] == [
        ("2030-01", "1000.00"),
        ("2030-02", "1000.00"),
        ("2030-03", "1000.00"),
    ]


class Jan2030(date):
    @classmethod
    def today(cls) -> "Jan2030":
        return cls(2030, 1, 22)


def test_card_summary_and_pay_invoice(user: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cards, "date", Jan2030)
    card = new_card(user)
    add_expense(user, amount="200.00", card_id=card["id"], purchase_date="2030-01-05")
    add_expense(user, amount="50.00", card_id=card["id"], purchase_date="2030-01-20")
    [summary] = user.get("/api/cards").json()
    assert summary["used"] == "250.00"
    assert summary["available"] == "2750.00"
    assert summary["best_day"] == 3
    invoices = {i["month"]: i for i in user.get(f"/api/cards/{card['id']}/invoices").json()}
    assert invoices["2030-02"]["total"] == "250.00"
    assert invoices["2030-02"]["count"] == 2
    paid = user.post(f"/api/cards/{card['id']}/invoices/2030-02/pay", json={"paid": True})
    assert paid.json() == {"updated": 2}
    items = user.get(f"/api/cards/{card['id']}/invoices/2030-02").json()
    assert all(i["paid"] for i in items)
    # Pagar a fatura não cria outra conta: o mês continua com as duas compras só.
    feb = user.get("/api/months/2030-02").json()
    assert len(feb["expenses"]) == 2
    assert user.get("/api/cards").json()[0]["used"] == "0.00"


def test_calendar_shows_invoice_not_each_purchase(user: TestClient) -> None:
    card = new_card(user)
    add_expense(
        user, description="Ifood", amount="40.00", card_id=card["id"], purchase_date="2030-01-05"
    )
    add_expense(
        user, description="Uber", amount="25.00", card_id=card["id"], purchase_date="2030-01-06"
    )
    events = user.get("/api/calendar/2030-02").json()["events"]
    kinds = [(e["kind"], e["description"], e["amount"]) for e in events]
    assert ("invoice", "Fatura Nubank", "65.00") in kinds
    assert not any(e["description"] in ("Ifood", "Uber") for e in events)
    # A fatura fecha dia 03/02 e vence dia 10/02; em janeiro não há nada do cartão.
    assert ("invoice_close", "Fecha a fatura Nubank", "65.00") in kinds
    january = user.get("/api/calendar/2030-01").json()["events"]
    assert not any(e["kind"].startswith("invoice") for e in january)


def test_card_belongs_to_owner(user: TestClient, outbox: list[OutgoingEmail]) -> None:
    card = new_card(user)
    user.post("/api/auth/logout")
    create_verified_user(user, outbox, "bia@example.com")
    login(user, "bia@example.com")
    response = user.post(
        f"/api/months/{MONTH}/expenses",
        json={"description": "X", "amount": "1.00", "card_id": card["id"]},
    )
    assert response.status_code == 404
    assert user.get("/api/cards").json() == []


# ---------------------------------------------------------------- lote


def test_bulk_actions(user: TestClient) -> None:
    ids = [add_expense(user, description=f"Conta {i}")[0]["id"] for i in range(3)]
    lazer = category_id(user, "Lazer")
    assert user.post("/api/expenses/bulk", json={"ids": ids[:2], "action": "pay"}).json() == {
        "count": 2
    }
    user.post("/api/expenses/bulk", json={"ids": ids, "action": "category", "category_id": lazer})
    expenses = user.get(f"/api/months/{MONTH}").json()["expenses"]
    assert sorted(e["paid"] for e in expenses) == [False, True, True]
    assert {e["category_id"] for e in expenses} == {lazer}
    user.post("/api/expenses/bulk", json={"ids": ids[:1], "action": "delete"})
    assert len(user.get(f"/api/months/{MONTH}").json()["expenses"]) == 2


def test_bulk_ignores_other_users(user: TestClient, outbox: list[OutgoingEmail]) -> None:
    [mine] = add_expense(user)
    user.post("/api/auth/logout")
    create_verified_user(user, outbox, "bia@example.com")
    login(user, "bia@example.com")
    response = user.post("/api/expenses/bulk", json={"ids": [mine["id"]], "action": "delete"})
    assert response.json() == {"count": 0}


# ---------------------------------------------------------------- regras


def test_rules_drive_suggestion_and_new_expenses(user: TestClient) -> None:
    lazer = category_id(user, "Lazer")
    rule = user.post("/api/rules", json={"pattern": "Ubér", "category_id": lazer}).json()
    assert rule["pattern"] == "uber"
    found = user.get("/api/suggest/category", params={"description": "Uber Black"}).json()
    assert found == {"category_id": lazer, "name": "Lazer", "source": "rule"}
    [expense] = add_expense(user, description="UBER *TRIP")
    assert expense["category_id"] == lazer
    # Mesma regra de novo: troca a categoria em vez de duplicar.
    transporte = category_id(user, "Transporte")
    user.post("/api/rules", json={"pattern": "uber", "category_id": transporte})
    assert [r["category_id"] for r in user.get("/api/rules").json()] == [transporte]
    assert user.delete(f"/api/rules/{rule['id']}").status_code == 204
    assert user.get("/api/rules").json() == []


# ---------------------------------------------------------------- saldo dia a dia


def test_daily_forecast_and_can_spend(user: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    user.post(
        f"/api/months/{MONTH}/incomes",
        json={"description": "Salário", "amount": "3000.00", "day": 5},
    )
    add_expense(user, description="Aluguel", amount="1200.00", due_date="2030-01-03")
    add_expense(user, description="Luz", amount="300.00", due_date="2030-01-20")
    user.post(
        "/api/planned", json={"date": "2030-01-25", "description": "Presente", "amount": "100.00"}
    )

    class FakeDate(date):
        @classmethod
        def today(cls) -> "FakeDate":
            return cls(2030, 1, 22)

    monkeypatch.setattr(daily, "date", FakeDate)
    data = user.get(f"/api/daily?month={MONTH}").json()
    balances = {d["date"]: d["balance"] for d in data["days"]}
    assert balances["2030-01-03"] == "-1200.00"
    assert balances["2030-01-05"] == "1800.00"
    assert data["first_negative"] == "2030-01-03"
    assert data["end_balance"] == "1400.00"
    assert data["planned_total"] == "100.00"
    # Mês com saldo negativo no começo: o limite seguro é o menor saldo (zero).
    assert data["can_spend"]["days_left"] == 10
    assert data["can_spend"]["today"] == "0.00"


def test_can_spend_divides_what_is_left(user: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    user.post(f"/api/months/{MONTH}/incomes", json={"description": "Salário", "amount": "1000.00"})
    add_expense(user, description="Aluguel", amount="500.00", due_date="2030-01-10")

    class FakeDate(date):
        @classmethod
        def today(cls) -> "FakeDate":
            return cls(2030, 1, 22)

    monkeypatch.setattr(daily, "date", FakeDate)
    can = user.get(f"/api/daily?month={MONTH}").json()["can_spend"]
    assert can == {"today": "50.00", "rest_of_month": "500.00", "days_left": 10}


# ---------------------------------------------------------------- assinaturas


def test_subscriptions_fixed_costs_and_candidates(user: TestClient) -> None:
    user.post(
        "/api/recurring",
        json={
            "kind": "expense",
            "description": "Seguro",
            "amount": "600.00",
            "start_month": MONTH,
            "interval_months": 6,
        },
    )
    for month in ("2029-10", "2029-11", "2029-12", MONTH):
        add_expense(user, month, description="Spotify", amount="21.90")
    add_expense(user, "2029-12", description="Presente", amount="80.00")
    data = user.get("/api/subscriptions").json()
    [seguro] = data["fixed"]
    assert (seguro["monthly"], seguro["yearly"]) == ("100.00", "1200.00")
    assert [c["description"] for c in data["candidates"]] == ["Spotify"]
    assert data["candidates"][0]["yearly"] == "262.80"
    promoted = user.post(
        "/api/subscriptions/promote", json={"description": "Spotify", "amount": "21.90"}
    ).json()
    assert promoted["start_month"] == "2030-02"
    assert user.get("/api/subscriptions").json()["candidates"] == []


def test_money_split_total() -> None:
    assert budget_service._split_amount(Decimal("100.00"), 3, "total") == [
        Decimal("33.34"),
        Decimal("33.33"),
        Decimal("33.33"),
    ]


def test_card_payment_detection() -> None:
    from app.services.statement_import import is_card_payment

    assert is_card_payment("PAGAMENTO DE FATURA NUBANK")
    assert is_card_payment("Pgto Fatura Cartão")
    assert not is_card_payment("Mercado Assaí")
