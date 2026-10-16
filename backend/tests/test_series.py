"""Construtor "Monte sua análise": séries e análises salvas."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.email import OutgoingEmail
from tests.conftest import create_verified_user, login
from tests.test_analysis import category_id, investment
from tests.test_analysis import expense as add_expense
from tests.test_analysis import income as add_income

Outbox = list[OutgoingEmail]


@pytest.fixture
def user(client: TestClient, outbox: Outbox) -> TestClient:
    create_verified_user(client, outbox)
    login(client)
    # Renda de 5000 por mês; moradia 2000/2000/2100 e lazer 300/500/0 (jan, fev, mar).
    for month, lazer, moradia in (
        ("2030-01", "300", "2000"),
        ("2030-02", "500", "2000"),
        ("2030-03", None, "2100"),
    ):
        add_income(client, "5000", month)
        add_expense(client, moradia, "Moradia", month)
        if lazer:
            add_expense(client, lazer, "Lazer", month)
    return client


def series(client: TestClient, **config: Any) -> dict[str, Any]:
    body = {"period": "custom", "start": "2030-01", "end": "2030-03", **config}
    response = client.post("/api/analysis/series", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_expenses_by_month(user: TestClient) -> None:
    data = series(user, metric="expenses", group="month")
    assert [label["key"] for label in data["labels"]] == ["2030-01", "2030-02", "2030-03"]
    assert data["series"][0]["values"] == [2300.0, 2500.0, 2100.0]
    assert data["total"] == 6900.0
    assert data["unit"] == "money"


def test_savings_rate_is_percent_and_averaged(user: TestClient) -> None:
    data = series(user, metric="savings_rate", group="month")
    assert data["series"][0]["values"] == [54.0, 50.0, 58.0]
    assert data["unit"] == "percent"
    assert data["total"] == 54.0


def test_balance_and_income(user: TestClient) -> None:
    assert series(user, metric="balance", group="month")["series"][0]["values"] == [
        2700.0,
        2500.0,
        2900.0,
    ]
    assert series(user, metric="income", group="month")["total"] == 15000.0


def test_by_category_sorted_with_colors(user: TestClient) -> None:
    data = series(user, metric="expenses", group="category")
    assert [label["label"] for label in data["labels"]] == ["Moradia", "Lazer"]
    assert data["labels"][0]["color"]
    assert data["series"][0]["values"] == [6100.0, 800.0]


def test_month_by_category_is_stacked(user: TestClient) -> None:
    data = series(user, metric="expenses", group="month_category")
    names = [s["name"] for s in data["series"]]
    assert names == ["Moradia", "Lazer"]
    assert data["series"][1]["values"] == [300.0, 500.0, 0.0]


def test_essential_split(user: TestClient) -> None:
    data = series(user, metric="expenses", group="type")
    assert [label["label"] for label in data["labels"]] == ["Essencial", "Não essencial"]
    assert data["series"][0]["values"] == [6100.0, 800.0]
    by_month = series(user, metric="expenses", group="month_type")
    assert by_month["series"][1]["values"] == [300.0, 500.0, 0.0]


def test_category_filter(user: TestClient) -> None:
    lazer = category_id(user, "Lazer")
    data = series(user, metric="expenses", group="month", categories=[lazer])
    assert data["series"][0]["values"] == [300.0, 500.0, 0.0]


def test_compare_previous_period(user: TestClient) -> None:
    add_expense(user, "1000", "Moradia", "2029-12")
    data = series(
        user, metric="expenses", group="month", start="2030-02", end="2030-03", compare="previous"
    )
    assert data["compare"]["name"] == "Período anterior"
    assert data["compare"]["values"] == [1000.0, 2300.0]
    assert data["compare_total"] == 3300.0


def test_compare_last_year_by_category(user: TestClient) -> None:
    add_expense(user, "250", "Lazer", "2029-02")
    data = series(
        user,
        metric="expenses",
        group="category",
        start="2030-02",
        end="2030-02",
        compare="last_year",
    )
    labels = [label["label"] for label in data["labels"]]
    assert data["compare"]["values"][labels.index("Lazer")] == 250.0
    assert data["compare"]["values"][labels.index("Moradia")] == 0.0


def test_compare_average_is_flat_line(user: TestClient) -> None:
    data = series(
        user, metric="expenses", group="month", start="2030-03", end="2030-03", compare="average"
    )
    # Média dos meses com dados entre mar/2029 e fev/2030: jan (2300) e fev (2500).
    assert data["compare"]["values"] == [2400.0]


def test_investments_by_kind(user: TestClient) -> None:
    investment(user, kind="tesouro", current_value="3000", invested_amount="2800")
    investment(user, kind="renda_fixa", current_value="1000")
    data = series(user, metric="investments", group="kind")
    assert [label["label"] for label in data["labels"]] == ["Tesouro Direto", "Renda fixa"]
    assert data["total"] == 4000.0


@pytest.mark.parametrize(
    "config",
    [
        {"metric": "income", "group": "category"},
        {"metric": "investments", "group": "month"},
        {"metric": "expenses", "group": "kind"},
        {"metric": "expenses", "group": "month", "period": "custom", "start": None},
        {"metric": "expenses", "group": "month", "chart": "pizza"},
    ],
)
def test_invalid_combinations_are_rejected(user: TestClient, config: dict[str, Any]) -> None:
    assert (
        user.post(
            "/api/analysis/series",
            json={"period": "custom", "start": "2030-01", "end": "2030-03", **config},
        ).status_code
        == 422
    )


def test_preset_period_ends_in_current_month(user: TestClient) -> None:
    data = user.post(
        "/api/analysis/series", json={"metric": "expenses", "group": "month", "period": "3m"}
    ).json()
    assert len(data["labels"]) == 3


def test_long_custom_period_is_refused(user: TestClient) -> None:
    body = {
        "metric": "expenses",
        "group": "month",
        "period": "custom",
        "start": "2020-01",
        "end": "2030-12",
    }
    assert user.post("/api/analysis/series", json=body).status_code == 422


# ---------------------------------------------------------------- análises salvas


def test_saved_analyses_crud(user: TestClient) -> None:
    config = {"metric": "expenses", "group": "month_category", "period": "12m", "chart": "stacked"}
    created = user.post(
        "/api/analysis/saved", json={"name": "Lazer no ano", "config": config, "pinned": True}
    )
    assert created.status_code == 201, created.text
    item = created.json()
    assert item["config"]["chart"] == "stacked" and item["pinned"] is True

    renamed = user.patch(
        f"/api/analysis/saved/{item['id']}", json={"name": "Lazer 12 meses", "pinned": False}
    )
    assert renamed.json()["name"] == "Lazer 12 meses" and renamed.json()["pinned"] is False

    assert [s["name"] for s in user.get("/api/analysis/saved").json()] == ["Lazer 12 meses"]
    assert user.delete(f"/api/analysis/saved/{item['id']}").status_code == 204
    assert user.get("/api/analysis/saved").json() == []


def test_saved_analyses_are_private(user: TestClient, client: TestClient, outbox: Outbox) -> None:
    config = {"metric": "income", "group": "month"}
    item = user.post("/api/analysis/saved", json={"name": "Minha", "config": config}).json()
    client.post("/api/auth/logout")
    create_verified_user(client, outbox, "outra@example.com")
    login(client, "outra@example.com")
    assert client.get("/api/analysis/saved").json() == []
    assert client.delete(f"/api/analysis/saved/{item['id']}").status_code == 404
