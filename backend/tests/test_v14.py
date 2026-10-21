"""v1.4: vale-refeição como conta, chave Pix, MEI e aviso diário."""

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User
from app.services import budget as budget_service
from tests.conftest import create_verified_user, login
from tests.test_budget import Outbox, add_expense, category_id, month

MONTH = "2030-01"


@pytest.fixture
def user(client: TestClient, outbox: Outbox) -> TestClient:
    create_verified_user(client, outbox)
    login(client)
    return client


@pytest.fixture(autouse=True)
def fixed_current_month(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(budget_service, "current_month", lambda *_: date(2030, 1, 1))


# ---------------------------------------------------------------- vale-refeição


def test_meal_voucher_account_gets_monthly_top_up_and_only_pays_food(user: TestClient) -> None:
    food = category_id(user, "Alimentação")
    out = user.post(
        "/api/accounts",
        json={"name": "VR", "kind": "benefit", "benefit_amount": "800.00", "benefit_day": 5},
    )
    assert out.status_code == 201, out.text
    account = out.json()
    assert (account["benefit_category_id"], account["benefit_amount"], account["benefit_day"]) == (
        food,
        "800.00",
        5,
    )
    # A recarga é uma renda fixa ligada ao vale: entra no orçamento de todo mês.
    [recharge] = [i for i in month(user)["incomes"] if i["account_id"] == account["id"]]
    assert (recharge["description"], recharge["amount"], recharge["day"]) == (
        "Recarga: VR",
        "800.00",
        5,
    )
    assert [i["account_id"] for i in month(user, "2030-02")["incomes"]] == [account["id"]]
    # Só paga a categoria do vale.
    wrong = user.post(
        f"/api/months/{MONTH}/expenses",
        json={
            "description": "Cinema",
            "amount": "40.00",
            "account_id": account["id"],
            "category_id": category_id(user, "Lazer"),
        },
    )
    assert wrong.status_code == 400 and "só paga despesas de Alimentação" in wrong.json()["message"]
    add_expense(
        user,
        description="Almoço",
        amount="35.00",
        account_id=account["id"],
        category_id=food,
        paid=True,
    )
    # Mudar o valor da recarga vale a partir deste mês.
    user.patch(f"/api/accounts/{account['id']}", json={"benefit_amount": "900.00"})
    [recharge] = [i for i in month(user, "2030-02")["incomes"] if i["account_id"] == account["id"]]
    assert recharge["amount"] == "900.00"
    # Excluir o vale para a recarga.
    assert user.delete(f"/api/accounts/{account['id']}").status_code == 204
    assert all(i["description"] != "Recarga: VR" for i in month(user, "2030-03")["incomes"])


# ---------------------------------------------------------------- Pix e MEI


def test_pix_key_is_validated_and_normalized(user: TestClient) -> None:
    out = user.patch(
        "/api/me/finance-settings",
        json={"pix_key": "123.456.789-09", "pix_name": "Ana Souza", "pix_city": "Goiania"},
    )
    assert out.status_code == 200, out.text
    assert out.json()["pix_key"] == "12345678909"
    assert (
        user.patch("/api/me/finance-settings", json={"pix_key": "(62) 99999-0000"}).json()[
            "pix_key"
        ]
        == "+5562999990000"
    )
    assert user.patch("/api/me/finance-settings", json={"pix_key": "abc"}).status_code == 422
    me = user.get("/api/auth/me").json()
    assert (me["pix_name"], me["pix_city"]) == ("Ana Souza", "Goiania")


def test_mei_revenue_is_tracked_against_the_annual_limit(user: TestClient) -> None:
    user.patch("/api/me/finance-settings", json={"mei": True})
    assert user.get("/api/auth/me").json()["mei"] is True
    user.post(
        f"/api/months/{MONTH}/incomes",
        json={"description": "Serviço", "amount": "64800.00", "mei": True},
    )
    user.post(f"/api/months/{MONTH}/incomes", json={"description": "Salário", "amount": "3000.00"})
    summary = user.get("/api/mei?year=2030").json()
    assert (summary["total"], summary["limit"], summary["pct"], summary["count"]) == (
        "64800.00",
        "81000.00",
        80.0,
        1,
    )


# ---------------------------------------------------------------- aviso diário


def test_daily_push_only_for_who_turned_it_on(
    user: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import daily, notify, push

    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        push,
        "send",
        lambda db, u, kind, title, body, url="/", force=False: sent.append((kind, title)) or 1,
    )
    monkeypatch.setattr(
        daily,
        "forecast",
        lambda *a, **k: {
            "can_spend": {
                "today": Decimal("42.50"),
                "rest_of_month": Decimal("850"),
                "days_left": 20,
            }
        },
    )
    at = datetime(2030, 1, 12, 8, 5, tzinfo=ZoneInfo("America/Sao_Paulo"))
    notify.run_daily(db, at)
    assert [k for k, _ in sent if k == "daily"] == []
    out = user.patch("/api/push/prefs", json={"push_daily": True})
    assert out.status_code == 200 and out.json()["push_daily"] is True
    notify.run_daily(db, at)
    notify.run_daily(db, at)  # não repete no mesmo dia
    assert [t for k, t in sent if k == "daily"] == ["Disponível hoje: R$ 42,50"]
    me = db.scalar(select(User).where(User.email == "ana@example.com"))
    assert me is not None and me.push_daily is True


def test_mei_warns_once_at_80_percent(user: TestClient) -> None:
    user.patch("/api/me/finance-settings", json={"mei": True})
    user.post(
        f"/api/months/{MONTH}/incomes",
        json={"description": "Serviço", "amount": "60000.00", "mei": True},
    )
    assert not [i for i in user.get("/api/inbox").json() if i["title"].startswith("MEI:")]
    user.post(
        f"/api/months/{MONTH}/incomes",
        json={"description": "Serviço 2", "amount": "5000.00", "mei": True},
    )
    user.post(
        f"/api/months/{MONTH}/incomes",
        json={"description": "Serviço 3", "amount": "1000.00", "mei": True},
    )
    warnings = [i for i in user.get("/api/inbox").json() if i["title"].startswith("MEI:")]
    assert [w["title"] for w in warnings] == ["MEI: 80% do teto anual"]
