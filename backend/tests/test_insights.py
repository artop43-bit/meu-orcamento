"""Consultor financeiro, alertas, tendências, limites por categoria e convite do 2FA."""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.email import OutgoingEmail
from app.core.months import add_months, current_month, format_month
from tests import test_analysis
from tests.conftest import create_verified_user, login
from tests.test_analysis import category_id, investment

Outbox = list[OutgoingEmail]
MONTH = "2030-06"


@pytest.fixture
def user(client: TestClient, outbox: Outbox) -> TestClient:
    create_verified_user(client, outbox)
    login(client)
    return client


def income(client: TestClient, amount: str, month: str = MONTH) -> None:
    test_analysis.income(client, amount, month)


def expense(
    client: TestClient, amount: str, category: str | None, month: str = MONTH, **extra: Any
) -> None:
    test_analysis.expense(client, amount, category, month, **extra)


def insights(client: TestClient, month: str = MONTH) -> dict[str, Any]:
    response = client.get(f"/api/analysis/insights?month={month}")
    assert response.status_code == 200, response.text
    return response.json()


def titles(data: dict[str, Any], key: str = "alerts") -> list[str]:
    return [m["title"] for m in data[key]]


def before(months: int, base: str = MONTH) -> str:
    year, month = map(int, base.split("-"))
    return format_month(add_months(date(year, month, 1), -months))


# ---------------------------------------------------------------- humor do mês


def test_empty_month_invites_to_start(user: TestClient) -> None:
    data = insights(user)
    assert data["mood"] == "empty"
    assert data["messages"] == [] and data["alerts"] == []


@pytest.mark.parametrize(
    ("spent", "mood"),
    [("3000", "great"), ("4400", "good"), ("4800", "attention"), ("5600", "concern")],
)
def test_mood_follows_how_much_was_saved(user: TestClient, spent: str, mood: str) -> None:
    income(user, "5000", MONTH)
    expense(user, spent, "Moradia", MONTH)
    data = insights(user)
    assert data["mood"] == mood
    if mood == "great":
        assert data["headline"] == "Taxa de poupança acima da meta"
        assert "40%" in data["summary"]
    if mood == "concern":
        assert "negativo" in data["headline"]
        assert "R$ 600,00" in data["summary"]


def test_almost_all_income_committed_raises_alert(user: TestClient) -> None:
    income(user, "5000")
    expense(user, "4750", "Moradia")
    assert "Orçamento próximo do limite" in titles(insights(user))


def test_income_missing_is_a_concern(user: TestClient) -> None:
    expense(user, "300", "Lazer")
    data = insights(user)
    assert data["mood"] == "concern"
    assert data["savings_pct"] is None


# ---------------------------------------------------------------- comparação com a média


def history_months(client: TestClient, spent: str, count: int = 3) -> None:
    for back in range(1, count + 1):
        month = before(back)
        income(client, "5000", month)
        expense(client, spent, "Alimentação", month)


def test_praise_for_spending_less_than_average_and_streak(user: TestClient) -> None:
    history_months(user, "4000")
    income(user, "5000")
    expense(user, "3000", "Alimentação")
    data = insights(user)
    praise = titles(data, "messages")
    assert "Despesas 25% abaixo da média" in praise
    assert "4 meses consecutivos com saldo positivo" in praise


def test_spending_above_average_and_category_jump(user: TestClient) -> None:
    history_months(user, "600")
    income(user, "5000")
    expense(user, "900", "Alimentação")
    data = insights(user)
    assert "Despesas 50% acima da média" in titles(data, "messages")
    assert "Alimentação acima da média" in titles(data)


def test_repeated_red_months_get_a_stronger_message(user: TestClient) -> None:
    income(user, "3000", before(1))
    expense(user, "3500", "Moradia", before(1))
    income(user, "3000")
    expense(user, "3400", "Moradia")
    assert "Resultados negativos recorrentes" in titles(insights(user), "messages")


# ---------------------------------------------------------------- limites por categoria


def set_limit(client: TestClient, name: str, limit: str | None) -> dict[str, Any]:
    response = client.patch(
        f"/api/categories/{category_id(client, name)}", json={"monthly_limit": limit}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_category_limit_near_and_over(user: TestClient) -> None:
    assert Decimal(set_limit(user, "Lazer", "300")["monthly_limit"]) == 300
    income(user, "5000")
    expense(user, "250", "Lazer")
    data = insights(user)
    assert "Lazer: limite próximo" in titles(data)

    month = user.get(f"/api/months/{MONTH}").json()
    lazer = next(c for c in month["summary"]["by_category"] if c["name"] == "Lazer")
    assert Decimal(lazer["limit"]) == 300 and lazer["limit_pct"] == pytest.approx(83.3)

    expense(user, "100", "Lazer")
    alerts = insights(user)["alerts"]
    assert alerts[0]["title"] == "Limite de Lazer excedido"  # perigo vem primeiro
    assert alerts[0]["tone"] == "danger"

    # Tirar o limite volta a deixar a categoria livre.
    assert set_limit(user, "Lazer", None)["monthly_limit"] is None
    assert not any("Lazer" in t for t in titles(insights(user)))


def test_limit_must_be_positive(user: TestClient) -> None:
    response = user.patch(
        f"/api/categories/{category_id(user, 'Lazer')}", json={"monthly_limit": "0"}
    )
    assert response.status_code == 422


# ---------------------------------------------------------------- contas e próximos meses


def test_overdue_bills_are_flagged(user: TestClient) -> None:
    last = add_months(current_month(), -1)
    month = format_month(last)
    income(user, "4000", month)
    expense(user, "120", "Serviços", month, due_date=last.replace(day=5).isoformat())
    alert = next(a for a in insights(user, month)["alerts"] if "atraso" in a["title"])
    assert alert["tone"] == "danger"
    assert "R$ 120,00" in alert["text"]


def test_next_month_in_the_red_is_predicted(user: TestClient) -> None:
    for kind, amount in (("income", "2000"), ("expense", "2500")):
        response = user.post(
            "/api/recurring",
            json={
                "kind": kind,
                "description": kind,
                "amount": amount,
                "category_id": category_id(user, "Moradia") if kind == "expense" else None,
                "start_month": MONTH,
            },
        )
        assert response.status_code == 201, response.text
    assert "Projeção negativa para o próximo mês" in titles(insights(user))


# ---------------------------------------------------------------- reserva e metas


def test_reserve_advice(user: TestClient) -> None:
    income(user, "5000")
    expense(user, "3000", "Moradia")
    assert "Reserva de emergência não iniciada" in titles(insights(user), "messages")

    investment(user, current_value="20000", invested_amount="18000", is_emergency_reserve=True)
    assert "Reserva de emergência completa" in titles(insights(user), "messages")


def test_goal_out_of_pace(user: TestClient) -> None:
    income(user, "5000")
    expense(user, "4800", "Moradia")
    target = add_months(current_month(), 10)
    response = user.post(
        "/api/goals",
        json={"name": "Viagem", "target_amount": "10000", "target_date": target.isoformat()},
    )
    assert response.status_code == 201
    alert = next(a for a in insights(user)["alerts"] if "Viagem" in a["title"])
    assert alert["title"] == 'Meta "Viagem" abaixo do ritmo necessário'
    assert "R$ 1.000,00 por mês" in alert["text"]


# ---------------------------------------------------------------- tendências


def test_trends(user: TestClient) -> None:
    history_months(user, "800")
    income(user, "5000")
    expense(user, "1000", "Alimentação")
    expense(user, "200", "Lazer")
    income(user, "4000", before(12))
    expense(user, "3000", "Moradia", before(12))
    investment(user, invested_amount="1000", current_value="1100")

    response = user.get(f"/api/analysis/trends?until={MONTH}&months=12")
    assert response.status_code == 200, response.text
    data = response.json()
    assert len(data["months"]) == 12
    assert data["months"][-1]["month"] == MONTH
    assert data["months"][-1]["savings_pct"] == 76.0
    names = [c["name"] for c in data["categories"]]
    assert names[0] == "Alimentação"
    assert "Lazer" in names
    assert all(len(c["totals"]) == 12 for c in data["categories"])
    assert Decimal(data["averages"]["expenses_3m"]) == Decimal("933.33")
    assert data["same_month_last_year"]["month"] == before(12)
    assert Decimal(data["same_month_last_year"]["expenses"]) == Decimal("3000")
    assert Decimal(data["wealth"]["return_value"]) == Decimal("100")


def test_insights_require_login(client: TestClient) -> None:
    assert client.get("/api/analysis/insights").status_code == 401
    assert client.get("/api/analysis/trends").status_code == 401


# ---------------------------------------------------------------- convite do 2FA


def test_two_factor_prompt_can_be_dismissed(user: TestClient) -> None:
    assert user.get("/api/auth/me").json()["twofa_prompt_dismissed"] is False
    assert user.post("/api/auth/2fa/prompt", json={"dismissed": True}).status_code == 204
    assert user.get("/api/auth/me").json()["twofa_prompt_dismissed"] is True
    assert user.post("/api/auth/2fa/prompt", json={"dismissed": False}).status_code == 204
    assert user.get("/api/auth/me").json()["twofa_prompt_dismissed"] is False


def test_security_tip_is_last_and_respects_dismissal(user: TestClient) -> None:
    income(user, "5000")
    expense(user, "3000", "Moradia")
    assert insights(user)["messages"][-1]["title"] == "Segurança da conta"
    user.post("/api/auth/2fa/prompt", json={"dismissed": True})
    assert "Segurança da conta" not in titles(insights(user), "messages")


def test_current_month_is_described_as_in_progress(user: TestClient) -> None:
    month = format_month(current_month())
    income(user, "5000", month)
    expense(user, "1000", "Moradia", month)
    data = insights(user, month)
    assert data["in_progress"] is True
    assert data["headline"] == "Desempenho acima da meta"
    assert data["summary"].startswith("Parcial do mês: poupança de")
