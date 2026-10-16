from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.months import add_months, current_month, format_month
from app.demo import DEMO_EMAIL, DemoNotAllowed, seed_demo
from tests.conftest import login


def test_empty_demo_account_for_qa(client: TestClient, db: Session) -> None:
    password, created = seed_demo(db, with_data=False)
    assert created
    assert login(client, DEMO_EMAIL, password).json()["status"] == "ok"
    month = client.get(f"/api/months/{format_month(current_month())}").json()
    assert month["expenses"] == [] and month["incomes"] == []
    assert len(client.get("/api/categories").json()) == 8
    assert client.get("/api/goals").json() == []


def test_reset_erases_the_demo_data(client: TestClient, db: Session) -> None:
    seed_demo(db, with_data=True)
    password, created = seed_demo(db, reset=True, with_data=False)
    assert created
    login(client, DEMO_EMAIL, password)
    assert client.get("/api/investments").json() == []


def test_demo_account_with_sample_data(client: TestClient, db: Session) -> None:
    password, created = seed_demo(db)
    assert created

    # Já confirmada: entra direto, sem e-mail.
    response = login(client, DEMO_EMAIL, password)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    month = client.get(f"/api/months/{format_month(current_month())}").json()
    descriptions = {e["description"] for e in month["expenses"]}
    assert {"Aluguel", "Internet", "Mercado", "Notebook"} <= descriptions
    assert Decimal(month["summary"]["income_total"]) == Decimal("5100.00")

    history = client.get("/api/history?months=6").json()
    assert all(p["has_data"] for p in history)
    assert len(client.get("/api/goals").json()) == 2
    assert len(client.get("/api/investments").json()) == 3

    score = client.get("/api/analysis/overview").json()["score"]
    assert score["score"] is not None

    # Cobre o sistema todo: um mês no vermelho, limites, análise fixada e alertas do consultor.
    assert any(Decimal(p["balance"]) < 0 for p in history)
    limits = {c["name"]: c["monthly_limit"] for c in client.get("/api/categories").json()}
    assert limits["Lazer"] and limits["Alimentação"]
    saved = client.get("/api/analysis/saved").json()
    assert [s["name"] for s in saved] == ["Gastos por categoria"] and saved[0]["pinned"]
    insights = client.get("/api/analysis/insights").json()
    assert insights["mood"] != "empty" and insights["alerts"]

    # Parcela do notebook continua nos próximos meses.
    later = client.get(f"/api/months/{format_month(add_months(current_month(), 6))}").json()
    assert any(e["description"] == "Notebook" for e in later["expenses"])


def test_running_again_only_resets_password(client: TestClient, db: Session) -> None:
    first, _ = seed_demo(db, with_data=True)
    second, created = seed_demo(db, with_data=True)
    assert not created
    assert first != second
    assert login(client, DEMO_EMAIL, first).status_code == 401
    assert login(client, DEMO_EMAIL, second).status_code == 200
    # Não duplica dados.
    assert len(client.get("/api/goals").json()) == 2


def test_demo_is_refused_in_production(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "environment", "production")
    with pytest.raises(DemoNotAllowed):
        seed_demo(db)
