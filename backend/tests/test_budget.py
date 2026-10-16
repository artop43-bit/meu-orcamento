from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.email import OutgoingEmail
from app.services import budget as budget_service
from tests.conftest import create_verified_user, login

Outbox = list[OutgoingEmail]
MONTH = "2030-01"


@pytest.fixture
def user(client: TestClient, outbox: Outbox) -> TestClient:
    create_verified_user(client, outbox)
    login(client)
    return client


@pytest.fixture(autouse=True)
def fixed_current_month(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(budget_service, "current_month", lambda: date(2030, 1, 1))


def category_id(client: TestClient, name: str) -> str:
    return next(c["id"] for c in client.get("/api/categories").json() if c["name"] == name)


def add_expense(client: TestClient, month: str = MONTH, **data: Any) -> list[dict[str, Any]]:
    payload = {"description": "Conta", "amount": "100.00", **data}
    response = client.post(f"/api/months/{month}/expenses", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def month(client: TestClient, value: str = MONTH) -> dict[str, Any]:
    response = client.get(f"/api/months/{value}")
    assert response.status_code == 200, response.text
    return response.json()


def descriptions(data: dict[str, Any], kind: str = "expenses") -> list[str]:
    return [item["description"] for item in data[kind]]


# ---------------------------------------------------------------- categorias


def test_new_account_gets_default_categories(user: TestClient) -> None:
    categories = user.get("/api/categories").json()
    names = {c["name"]: c["is_essential"] for c in categories}
    assert len(names) == 8
    assert names["Moradia"] is True
    assert names["Lazer"] is False


def test_category_crud(user: TestClient) -> None:
    created = user.post("/api/categories", json={"name": "Pets", "is_essential": True})
    assert created.status_code == 201

    duplicate = user.post("/api/categories", json={"name": "pets"})
    assert duplicate.status_code == 409

    cid = created.json()["id"]
    renamed = user.patch(f"/api/categories/{cid}", json={"name": "Animais"})
    assert renamed.json()["name"] == "Animais"

    add_expense(user, description="Ração", category_id=cid)
    assert user.delete(f"/api/categories/{cid}").status_code == 204
    # A conta continua existindo, agora sem categoria.
    expense = month(user)["expenses"][0]
    assert expense["category_id"] is None
    assert month(user)["summary"]["by_category"][0]["name"] == "Sem categoria"


# ---------------------------------------------------------------- mês


def test_empty_month(user: TestClient) -> None:
    data = month(user)
    assert data["month"] == MONTH
    assert data["incomes"] == []
    assert data["expenses"] == []
    assert Decimal(data["summary"]["balance"]) == 0
    assert data["summary"]["committed_pct"] is None


def test_month_summary(user: TestClient) -> None:
    user.post(f"/api/months/{MONTH}/incomes", json={"description": "Salário", "amount": "2300"})
    user.post(f"/api/months/{MONTH}/incomes", json={"description": "Benefício", "amount": "1100"})
    faculdade = add_expense(
        user, description="Faculdade", amount="563", category_id=category_id(user, "Educação")
    )[0]
    add_expense(user, description="Cinema", amount="37.50", category_id=category_id(user, "Lazer"))

    user.patch(f"/api/expenses/{faculdade['id']}", json={"paid": True})

    summary = month(user)["summary"]
    assert Decimal(summary["income_total"]) == Decimal("3400")
    assert Decimal(summary["expense_total"]) == Decimal("600.50")
    assert Decimal(summary["paid_total"]) == Decimal("563")
    assert Decimal(summary["pending_total"]) == Decimal("37.50")
    assert Decimal(summary["balance"]) == Decimal("2799.50")
    assert summary["committed_pct"] == 17.7
    assert Decimal(summary["essential_total"]) == Decimal("563")
    assert Decimal(summary["non_essential_total"]) == Decimal("37.50")
    assert [c["name"] for c in summary["by_category"]] == ["Educação", "Lazer"]


def test_paid_toggle_sets_and_clears_paid_at(user: TestClient) -> None:
    expense = add_expense(user)[0]
    paid = user.patch(f"/api/expenses/{expense['id']}", json={"paid": True}).json()
    assert paid["paid"] is True
    assert paid["paid_at"] is not None

    unpaid = user.patch(f"/api/expenses/{expense['id']}", json={"paid": False}).json()
    assert unpaid["paid_at"] is None


def test_expenses_sorted_by_due_date(user: TestClient) -> None:
    add_expense(user, description="Sem data")
    add_expense(user, description="Dia 20", due_date="2030-01-20")
    add_expense(user, description="Dia 5", due_date="2030-01-05")
    assert descriptions(month(user)) == ["Dia 5", "Dia 20", "Sem data"]


def test_validation_messages(user: TestClient) -> None:
    zero = user.post(f"/api/months/{MONTH}/expenses", json={"description": "X", "amount": "0"})
    assert zero.status_code == 422
    assert zero.json()["message"] == "O valor precisa ser maior que zero."

    cents = user.post(f"/api/months/{MONTH}/expenses", json={"description": "X", "amount": "1.999"})
    assert cents.json()["message"] == "Use no máximo 2 casas decimais."

    assert user.get("/api/months/2030-13").status_code == 400


def test_patch_cannot_null_required_fields(user: TestClient) -> None:
    expense = add_expense(user, description="Luz")[0]
    response = user.patch(f"/api/expenses/{expense['id']}", json={"description": None})
    assert response.status_code == 200
    assert response.json()["description"] == "Luz"


# ---------------------------------------------------------------- parcelas


def test_installments_span_months(user: TestClient) -> None:
    created = add_expense(
        user, description="Notebook", amount="300", installments=3, due_date="2030-01-31"
    )
    assert [e["month"] for e in created] == ["2030-01", "2030-02", "2030-03"]
    assert [e["installment_number"] for e in created] == [1, 2, 3]
    # Dia 31 vira o último dia de fevereiro.
    assert created[1]["due_date"] == "2030-02-28"

    feb = month(user, "2030-02")["expenses"][0]
    assert feb["installment_total"] == 3


def test_delete_installments_from_this_one_on(user: TestClient) -> None:
    created = add_expense(user, description="Celular", installments=4)
    second = created[1]["id"]
    assert user.delete(f"/api/expenses/{second}?scope=following").status_code == 204

    assert descriptions(month(user, "2030-01")) == ["Celular"]
    for value in ("2030-02", "2030-03", "2030-04"):
        assert month(user, value)["expenses"] == []


# ---------------------------------------------------------------- fixas


def test_recurring_expense_appears_in_opened_and_future_months(user: TestClient) -> None:
    month(user, MONTH)  # mês já aberto antes de criar a fixa
    response = user.post(
        "/api/recurring",
        json={
            "kind": "expense",
            "description": "Aluguel",
            "amount": "1200",
            "category_id": category_id(user, "Moradia"),
            "due_day": 10,
            "start_month": MONTH,
        },
    )
    assert response.status_code == 201

    january = month(user, MONTH)["expenses"]
    assert descriptions({"expenses": january}) == ["Aluguel"]
    assert january[0]["due_date"] == "2030-01-10"

    assert descriptions(month(user, "2030-05")) == ["Aluguel"]
    # Antes do início, nada.
    assert month(user, "2029-12")["expenses"] == []


def test_recurring_income(user: TestClient) -> None:
    user.post(
        "/api/recurring",
        json={"kind": "income", "description": "Salário", "amount": "2300", "start_month": MONTH},
    )
    assert descriptions(month(user, "2030-03"), "incomes") == ["Salário"]


def test_deleted_recurring_instance_does_not_come_back(user: TestClient) -> None:
    user.post(
        "/api/recurring",
        json={
            "kind": "expense",
            "description": "Internet",
            "amount": "99.90",
            "start_month": MONTH,
        },
    )
    instance = month(user)["expenses"][0]
    user.delete(f"/api/expenses/{instance['id']}")

    assert month(user)["expenses"] == []
    assert descriptions(month(user, "2030-02")) == ["Internet"]


def test_delete_recurring_from_this_month_on(user: TestClient) -> None:
    item = user.post(
        "/api/recurring",
        json={"kind": "expense", "description": "Academia", "amount": "90", "start_month": MONTH},
    ).json()
    month(user, "2030-02")
    march = month(user, "2030-03")["expenses"][0]

    user.delete(f"/api/expenses/{march['id']}?scope=following")

    assert descriptions(month(user, "2030-02")) == ["Academia"]
    assert month(user, "2030-03")["expenses"] == []
    assert month(user, "2030-06")["expenses"] == []
    recurring = user.get("/api/recurring").json()
    assert recurring[0]["id"] == item["id"]
    assert recurring[0]["end_month"] == "2030-02"


def test_update_recurring_propagates_to_unpaid_current_and_future(user: TestClient) -> None:
    item = user.post(
        "/api/recurring",
        json={
            "kind": "expense",
            "description": "Aluguel",
            "amount": "1200",
            "start_month": "2029-12",
        },
    ).json()
    december = month(user, "2029-12")["expenses"][0]
    january = month(user, "2030-01")["expenses"][0]
    month(user, "2030-02")
    user.patch(f"/api/expenses/{january['id']}", json={"paid": True})

    user.patch(f"/api/recurring/{item['id']}", json={"amount": "1350"})

    assert Decimal(month(user, "2029-12")["expenses"][0]["amount"]) == Decimal("1200")  # passado
    assert Decimal(month(user, "2030-01")["expenses"][0]["amount"]) == Decimal("1200")  # pago
    assert Decimal(month(user, "2030-02")["expenses"][0]["amount"]) == Decimal("1350")
    assert Decimal(month(user, "2030-04")["expenses"][0]["amount"]) == Decimal("1350")
    assert december["id"] != january["id"]


def test_delete_recurring_keeps_past_and_current(user: TestClient) -> None:
    item = user.post(
        "/api/recurring",
        json={
            "kind": "expense",
            "description": "Streaming",
            "amount": "40",
            "start_month": "2029-12",
        },
    ).json()
    for value in ("2029-12", "2030-01", "2030-02"):
        month(user, value)

    assert user.delete(f"/api/recurring/{item['id']}").status_code == 204
    assert descriptions(month(user, "2029-12")) == ["Streaming"]
    assert descriptions(month(user, "2030-01")) == ["Streaming"]
    assert month(user, "2030-02")["expenses"] == []
    assert user.get("/api/recurring").json() == []


def test_recurring_invalid_period(user: TestClient) -> None:
    response = user.post(
        "/api/recurring",
        json={
            "kind": "expense",
            "description": "X",
            "amount": "10",
            "start_month": "2030-05",
            "end_month": "2030-01",
        },
    )
    assert response.status_code == 400


# ---------------------------------------------------------------- histórico


def test_history(user: TestClient) -> None:
    user.post("/api/months/2029-12/incomes", json={"description": "Salário", "amount": "2000"})
    add_expense(user, month="2029-12", amount="500")
    user.post(f"/api/months/{MONTH}/incomes", json={"description": "Salário", "amount": "2000"})
    paid = add_expense(user, amount="800")[0]
    user.patch(f"/api/expenses/{paid['id']}", json={"paid": True})

    points = user.get("/api/history?months=3&until=2030-01").json()
    assert [p["month"] for p in points] == ["2029-11", "2029-12", "2030-01"]
    assert points[0]["has_data"] is False
    assert Decimal(points[1]["balance"]) == Decimal("1500")
    assert points[1]["committed_pct"] == 25.0
    assert Decimal(points[2]["paid"]) == Decimal("800")


# ---------------------------------------------------------------- metas


def test_goals(user: TestClient) -> None:
    created = user.post(
        "/api/goals", json={"name": "Reserva de emergência", "target_amount": "10000"}
    )
    assert created.status_code == 201
    goal = created.json()
    assert goal["progress_pct"] == 0.0

    goal = user.post(f"/api/goals/{goal['id']}/contributions", json={"amount": "2500"}).json()
    assert goal["progress_pct"] == 25.0

    withdraw = user.post(f"/api/goals/{goal['id']}/contributions", json={"amount": "-3000"})
    assert withdraw.status_code == 400

    goal = user.post(f"/api/goals/{goal['id']}/contributions", json={"amount": "-500"}).json()
    assert Decimal(goal["current_amount"]) == Decimal("2000")

    renamed = user.patch(f"/api/goals/{goal['id']}", json={"name": "Reserva"}).json()
    assert renamed["name"] == "Reserva"

    assert user.delete(f"/api/goals/{goal['id']}").status_code == 204
    assert user.get("/api/goals").json() == []


# ---------------------------------------------------------------- isolamento entre usuários


def test_users_cannot_see_or_change_each_others_data(client: TestClient, outbox: Outbox) -> None:
    create_verified_user(client, outbox, "ana@example.com")
    create_verified_user(client, outbox, "bia@example.com")

    login(client, "ana@example.com")
    expense = add_expense(client, description="Segredo da Ana")[0]
    goal = client.post("/api/goals", json={"name": "Viagem", "target_amount": "5000"}).json()
    ana_category = category_id(client, "Moradia")
    client.post("/api/auth/logout")

    login(client, "bia@example.com")
    assert month(client)["expenses"] == []
    assert client.get("/api/goals").json() == []
    assert client.patch(f"/api/expenses/{expense['id']}", json={"amount": "1"}).status_code == 404
    assert client.delete(f"/api/expenses/{expense['id']}").status_code == 404
    assert (
        client.post(f"/api/goals/{goal['id']}/contributions", json={"amount": "1"}).status_code
        == 404
    )
    # Também não pode usar a categoria da Ana nas próprias contas.
    response = client.post(
        f"/api/months/{MONTH}/expenses",
        json={"description": "X", "amount": "1", "category_id": ana_category},
    )
    assert response.status_code == 404
    client.post("/api/auth/logout")

    login(client, "ana@example.com")
    assert descriptions(month(client)) == ["Segredo da Ana"]


def test_budget_requires_login(client: TestClient) -> None:
    assert client.get(f"/api/months/{MONTH}").status_code == 401
    assert client.get("/api/goals").status_code == 401


def test_expense_can_be_created_already_paid(user: TestClient) -> None:
    url = f"/api/months/{MONTH}/expenses"
    single = user.post(url, json={"description": "Mercado", "amount": "80", "paid": True}).json()
    assert single[0]["paid"] is True
    assert single[0]["paid_at"] is not None

    # Parcelada: só a primeira parcela já está paga.
    body = {"description": "TV", "amount": "100", "installments": 3, "paid": True}
    parcels = user.post(url, json=body).json()
    assert [p["paid"] for p in parcels] == [True, False, False]
