from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.email import OutgoingEmail
from app.services import budget as budget_service
from app.services.suggest import normalize
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


def plan(client: TestClient, **data: Any) -> dict[str, Any]:
    payload = {"date": "2030-02-15", "description": "Aniversário da Ana", "amount": "250.00"}
    response = client.post("/api/planned", json={**payload, **data})
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------- planejados


def test_planned_crud_and_filter_by_month(user: TestClient) -> None:
    item = plan(user, notes="Bolo e presente")
    plan(user, date="2030-03-10", description="IPVA", amount="1200.00")
    assert [p["description"] for p in user.get("/api/planned?month=2030-02").json()] == [
        "Aniversário da Ana"
    ]
    assert len(user.get("/api/planned").json()) == 2
    changed = user.patch(f"/api/planned/{item['id']}", json={"amount": "300.00"}).json()
    assert changed["amount"] == "300.00"
    assert user.delete(f"/api/planned/{item['id']}").status_code == 204
    assert len(user.get("/api/planned").json()) == 1


def test_confirm_planned_creates_expense_once(user: TestClient) -> None:
    item = plan(user, category_id=category_id(user, "Lazer"))
    response = user.post(f"/api/planned/{item['id']}/confirm", json={"paid": True})
    assert response.status_code == 201, response.text
    expense = response.json()
    assert expense["month"] == "2030-02"
    assert expense["due_date"] == "2030-02-15"
    assert expense["paid"] is True
    feb = user.get("/api/months/2030-02").json()
    assert [e["description"] for e in feb["expenses"]] == ["Aniversário da Ana"]
    again = user.post(f"/api/planned/{item['id']}/confirm", json={})
    assert again.status_code == 409


def test_planned_counts_in_projection_until_confirmed(user: TestClient) -> None:
    item = plan(user)
    points = user.get("/api/analysis/projection?start=2030-02&months=2").json()
    assert points[0]["planned"] == "250.00"
    assert points[0]["expenses"] == "250.00"
    assert points[1]["planned"] == "0.00"
    user.post(f"/api/planned/{item['id']}/confirm", json={})
    points = user.get("/api/analysis/projection?start=2030-02&months=1").json()
    # Agora é conta de verdade: não conta em dobro.
    assert points[0]["planned"] == "0.00"
    assert points[0]["expenses"] == "250.00"


def test_planned_belongs_to_owner(user: TestClient, outbox: list[OutgoingEmail]) -> None:
    item = plan(user)
    user.post("/api/auth/logout")
    create_verified_user(user, outbox, "bia@example.com")
    login(user, "bia@example.com")
    assert user.patch(f"/api/planned/{item['id']}", json={"amount": "1.00"}).status_code == 404
    assert user.get("/api/planned").json() == []


# ---------------------------------------------------------------- calendário


def test_calendar_lists_everything_with_dates(user: TestClient) -> None:
    user.post(
        f"/api/months/{MONTH}/incomes",
        json={"description": "Salário", "amount": "3000.00", "day": 5},
    )
    user.post(
        f"/api/months/{MONTH}/expenses",
        json={"description": "Aluguel", "amount": "1200.00", "due_date": "2030-01-10"},
    )
    user.post(
        f"/api/months/{MONTH}/expenses",
        json={"description": "TV", "amount": "100.00", "installments": 3, "due_date": "2030-01-20"},
    )
    user.post(f"/api/months/{MONTH}/expenses", json={"description": "Pão", "amount": "8.00"})
    plan(user, date="2030-01-25", description="Presente")
    data = user.get(f"/api/calendar/{MONTH}").json()
    events = [(e["date"], e["kind"], e["description"]) for e in data["events"]]
    assert events == [
        ("2030-01-05", "income", "Salário"),
        ("2030-01-10", "expense", "Aluguel"),
        ("2030-01-20", "installment", "TV"),
        ("2030-01-25", "planned", "Presente"),
        (None, "expense", "Pão"),
    ]


# ---------------------------------------------------------------- sugestões


def test_normalize() -> None:
    assert normalize("  Farmácia São João 2/10 ") == "farmacia sao joao"


def test_suggest_category_from_keywords(user: TestClient) -> None:
    found = user.get("/api/suggest/category", params={"description": "Uber pro trabalho"}).json()
    assert found["name"] == "Transporte"
    assert found["source"] == "keywords"
    assert user.get("/api/suggest/category", params={"description": "xyzzy"}).json() is None


def test_suggest_category_learns_from_history(user: TestClient) -> None:
    lazer = category_id(user, "Lazer")
    for _ in range(2):
        user.post(
            f"/api/months/{MONTH}/expenses",
            json={"description": "Uber", "amount": "20.00", "category_id": lazer},
        )
    found = user.get("/api/suggest/category", params={"description": "uber"}).json()
    assert found == {"category_id": lazer, "name": "Lazer", "source": "history"}


def test_description_autocomplete(user: TestClient) -> None:
    saude = category_id(user, "Saúde")
    for amount in ("50.00", "60.00"):
        user.post(
            f"/api/months/{MONTH}/expenses",
            json={
                "description": "Farmácia",
                "amount": amount,
                "category_id": saude,
                "payment_method": "debit",
            },
        )
    user.post(f"/api/months/{MONTH}/expenses", json={"description": "Café", "amount": "5.00"})
    found = user.get("/api/suggest/descriptions", params={"q": "farm"}).json()
    assert len(found) == 1
    assert found[0]["description"] == "Farmácia"
    assert found[0]["amount"] == "60.00"
    assert found[0]["category_id"] == saude
    assert found[0]["payment_method"] == "debit"
    assert found[0]["count"] == 2
