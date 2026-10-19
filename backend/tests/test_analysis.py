from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.email import OutgoingEmail
from app.services import indicators
from tests.conftest import create_verified_user, login

Outbox = list[OutgoingEmail]
MONTH = "2030-01"


@pytest.fixture
def user(client: TestClient, outbox: Outbox) -> TestClient:
    create_verified_user(client, outbox)
    login(client)
    return client


def category_id(client: TestClient, name: str) -> str:
    return next(c["id"] for c in client.get("/api/categories").json() if c["name"] == name)


def income(client: TestClient, amount: str, month: str = MONTH) -> None:
    response = client.post(
        f"/api/months/{month}/incomes", json={"description": "Renda", "amount": amount}
    )
    assert response.status_code == 201


def expense(
    client: TestClient, amount: str, category: str | None, month: str = MONTH, **extra: Any
) -> None:
    payload = {"description": "Conta", "amount": amount, **extra}
    if category:
        payload["category_id"] = category_id(client, category)
    response = client.post(f"/api/months/{month}/expenses", json=payload)
    assert response.status_code == 201, response.text


def investment(client: TestClient, **data: Any) -> dict[str, Any]:
    payload = {
        "name": "CDB",
        "kind": "renda_fixa",
        "invested_amount": "1000",
        "current_value": "1000",
        **data,
    }
    response = client.post("/api/investments", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def overview(client: TestClient, month: str = MONTH) -> dict[str, Any]:
    response = client.get(f"/api/analysis/overview?month={month}")
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------- score


def test_score_without_data(user: TestClient) -> None:
    score = overview(user)["score"]
    assert score["score"] is None
    assert score["label"] == "Sem dados"


def test_score_excellent(user: TestClient) -> None:
    income(user, "5000")
    expense(user, "2000", "Moradia")
    expense(user, "500", "Lazer")
    # 6 meses de gastos (2.500) guardados como reserva.
    investment(user, name="Reserva", current_value="15000", is_emergency_reserve=True)
    investment(user, name="Ações", kind="acoes", current_value="9999")  # não é reserva

    score = overview(user)["score"]
    assert score["score"] == 100
    assert score["label"] == "Excelente"
    assert score["reserve_months"] == 6.0
    assert {c["key"]: c["points"] for c in score["components"]} == {
        "balance": 30.0,
        "committed": 30.0,
        "reserve": 25.0,
        "consistency": 15.0,
    }
    assert score["tips"] == ["Indicadores equilibrados no período."]


def test_score_critical(user: TestClient) -> None:
    income(user, "1000")
    expense(user, "1500", "Moradia")

    score = overview(user)["score"]
    assert score["score"] == 0
    assert score["label"] == "Crítica"
    assert any("superam a renda" in tip for tip in score["tips"])
    assert any("reserva de emergência" in tip for tip in score["tips"])


def test_score_partial(user: TestClient) -> None:
    income(user, "4000")
    expense(user, "3000", "Moradia")  # 75% comprometido -> 15 de 30
    investment(user, current_value="4500", is_emergency_reserve=True)  # 1,5 mês -> 6,25 de 25

    score = overview(user)["score"]
    points = {c["key"]: c["points"] for c in score["components"]}
    assert points["committed"] == 15.0
    assert points["reserve"] == 6.2
    # 30 + 15 + 6,25 + 15 = 66,25
    assert score["score"] == 66
    assert score["label"] == "Boa"


def test_consistency_uses_recent_months(user: TestClient) -> None:
    income(user, "1000", "2029-12")
    expense(user, "2000", None, "2029-12")  # dezembro no negativo
    income(user, "3000")
    expense(user, "1000", None)

    consistency = next(
        c for c in overview(user)["score"]["components"] if c["key"] == "consistency"
    )
    assert consistency["points"] == 7.5
    assert consistency["detail"] == "1 de 2 meses recentes no positivo"


# ---------------------------------------------------------------- 50/30/20


def test_rule_50_30_20(user: TestClient) -> None:
    income(user, "5000")
    expense(user, "2000", "Moradia")
    expense(user, "500", "Lazer")

    rule = overview(user)["rule"]
    assert (rule["needs_pct"], rule["wants_pct"], rule["savings_pct"]) == (40.0, 10.0, 50.0)
    assert rule["needs_ok"] and rule["wants_ok"] and rule["savings_ok"]
    assert Decimal(rule["deficit"]) == 0


def test_rule_with_deficit(user: TestClient) -> None:
    income(user, "2000")
    expense(user, "1800", "Moradia")
    expense(user, "700", "Lazer")

    rule = overview(user)["rule"]
    assert rule["needs_ok"] is False
    assert rule["wants_ok"] is False
    assert rule["savings_ok"] is False
    assert Decimal(rule["savings"]) == 0
    assert Decimal(rule["deficit"]) == Decimal("500")


# ---------------------------------------------------------------- comparação


def test_compare_months(user: TestClient) -> None:
    income(user, "3000", "2029-12")
    expense(user, "1000", "Moradia", "2029-12")
    expense(user, "300", "Lazer", "2029-12")
    income(user, "3200")
    expense(user, "1000", "Moradia")
    expense(user, "600", "Lazer")
    expense(user, "150", "Saúde")

    response = user.get("/api/analysis/compare?a=2029-12&b=2030-01")
    assert response.status_code == 200
    data = response.json()
    assert Decimal(data["income"]["delta"]) == Decimal("200")
    assert Decimal(data["expenses"]["delta"]) == Decimal("450")
    assert Decimal(data["balance"]["delta"]) == Decimal("-250")

    rows = {row["name"]: row for row in data["categories"]}
    assert rows["Lazer"]["delta_pct"] == 100.0
    assert rows["Moradia"]["delta_pct"] == 0.0
    assert rows["Saúde"]["delta_pct"] is None  # não existia no mês A
    # Ordenado pela maior variação.
    assert data["categories"][0]["name"] == "Lazer"


# ---------------------------------------------------------------- projeção


def test_projection_uses_installments_and_recurring(user: TestClient) -> None:
    user.get(f"/api/months/{MONTH}")  # janeiro já aberto
    user.post(
        "/api/recurring",
        json={"kind": "income", "description": "Salário", "amount": "3000", "start_month": MONTH},
    )
    expense(user, "500", None, installments=3)
    expense(user, "200", None)  # só em janeiro

    response = user.get(f"/api/analysis/projection?start={MONTH}&months=4")
    assert response.status_code == 200
    points = response.json()
    assert [p["month"] for p in points] == ["2030-01", "2030-02", "2030-03", "2030-04"]
    assert [Decimal(p["income"]) for p in points] == [Decimal("3000")] * 4
    assert [Decimal(p["expenses"]) for p in points] == [
        Decimal("700"),
        Decimal("500"),
        Decimal("500"),
        Decimal("0"),
    ]
    assert [Decimal(p["cumulative"]) for p in points] == [
        Decimal("2300"),
        Decimal("4800"),
        Decimal("7300"),
        Decimal("10300"),
    ]


def test_projection_does_not_double_count_opened_months(user: TestClient) -> None:
    user.post(
        "/api/recurring",
        json={"kind": "expense", "description": "Aluguel", "amount": "1000", "start_month": MONTH},
    )
    user.get("/api/months/2030-02")  # fevereiro aberto: aluguel já lançado lá

    points = user.get(f"/api/analysis/projection?start={MONTH}&months=2").json()
    assert [Decimal(p["expenses"]) for p in points] == [Decimal("1000"), Decimal("1000")]


# ---------------------------------------------------------------- investimentos


def test_investments_crud_and_returns(user: TestClient) -> None:
    created = investment(
        user, name="Tesouro Selic", kind="tesouro", invested_amount="1000", current_value="1100"
    )
    assert Decimal(created["return_amount"]) == Decimal("100")
    assert created["return_pct"] == 10.0

    updated = user.patch(
        f"/api/investments/{created['id']}", json={"current_value": "900", "institution": "Banco X"}
    ).json()
    assert updated["return_pct"] == -10.0
    assert updated["institution"] == "Banco X"

    invalid = user.post(
        "/api/investments",
        json={"name": "X", "kind": "imoveis", "invested_amount": "1", "current_value": "1"},
    )
    assert invalid.status_code == 422

    assert user.delete(f"/api/investments/{created['id']}").status_code == 204
    assert user.get("/api/investments").json() == []


def test_investments_are_private(client: TestClient, outbox: Outbox) -> None:
    create_verified_user(client, outbox, "ana@example.com")
    create_verified_user(client, outbox, "bia@example.com")
    login(client, "ana@example.com")
    item = investment(client, is_emergency_reserve=True, current_value="50000")
    client.post("/api/auth/logout")

    login(client, "bia@example.com")
    assert client.get("/api/investments").json() == []
    assert client.patch(f"/api/investments/{item['id']}", json={"name": "x"}).status_code == 404
    # A reserva da Ana não entra no score da Bia.
    income(client, "1000")
    expense(client, "500", None)
    assert overview(client)["score"]["reserve_total"] == "0.00"


# ---------------------------------------------------------------- indicadores


@pytest.fixture(autouse=True)
def _clear_indicator_cache() -> None:
    indicators.clear_cache()


def test_indicators(user: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    values = {432: (10.5, "15/10/2026"), 4389: (10.4, "15/10/2026"), 13522: (4.2, "01/09/2026")}
    calls: list[int] = []

    def fake_fetch(code: int) -> tuple[float, str]:
        calls.append(code)
        return values[code]

    monkeypatch.setattr(indicators, "fetch_series", fake_fetch)
    data = user.get("/api/indicators").json()
    assert data["available"] is True
    assert data["selic"] == {"value": 10.5, "date": "15/10/2026"}
    assert data["ipca_12m"]["value"] == 4.2

    # Segunda chamada vem do cache.
    user.get("/api/indicators")
    assert len(calls) == 3


def test_indicators_when_central_bank_is_down(
    user: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(code: int) -> tuple[float, str]:
        raise TimeoutError("sem rede")

    monkeypatch.setattr(indicators, "fetch_series", broken)
    response = user.get("/api/indicators")
    assert response.status_code == 200
    assert response.json()["available"] is False
    assert response.json()["selic"] is None


def test_indicators_require_login(client: TestClient) -> None:
    assert client.get("/api/indicators").status_code == 401


def test_projection_splits_non_essential(user: TestClient) -> None:
    user.post(
        "/api/recurring",
        json={
            "kind": "expense",
            "description": "Aluguel",
            "amount": "1000",
            "category_id": category_id(user, "Moradia"),
            "start_month": MONTH,
        },
    )
    expense(user, "300", "Lazer", "2030-02")
    expense(user, "50", None, "2030-02")  # sem categoria conta como não essencial

    points = user.get(f"/api/analysis/projection?start={MONTH}&months=2").json()
    assert [Decimal(p["non_essential"]) for p in points] == [Decimal("0"), Decimal("350")]
    assert [Decimal(p["expenses"]) for p in points] == [Decimal("1000"), Decimal("1350")]
