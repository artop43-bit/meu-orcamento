"""v1.0 (B): mês financeiro pelo dia do salário, alertas inteligentes e divisão de despesas."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.email import OutgoingEmail
from app.core.months import current_month, cycle_date, cycle_range, month_of
from app.models import InboxItem, Income, NotificationLog, User
from app.services import alerts, daily, notify
from app.services import budget as budget_service
from tests.conftest import create_verified_user, login

TZ = ZoneInfo("America/Sao_Paulo")


@pytest.fixture(autouse=True)
def fixed_current_month(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(budget_service, "current_month", lambda *_: date(2030, 1, 1))


@pytest.fixture
def user(client: TestClient, outbox: list[OutgoingEmail]) -> TestClient:
    create_verified_user(client, outbox)
    login(client)
    return client


def me(db: Session) -> User:
    db.expire_all()
    return db.scalar(select(User).where(User.email == "ana@example.com"))  # type: ignore[return-value]


def expense(client: TestClient, month: str, **data: Any) -> dict[str, Any]:
    payload = {"description": "Conta", "amount": "100.00", **data}
    response = client.post(f"/api/months/{month}/expenses", json=payload)
    assert response.status_code == 201, response.text
    return response.json()[0]


# ---------------------------------------------------------------- mês financeiro


def test_cycle_helpers() -> None:
    assert month_of(date(2030, 11, 2), 5) == date(2030, 10, 1)
    assert month_of(date(2030, 11, 5), 5) == date(2030, 11, 1)
    assert month_of(date(2030, 11, 2)) == date(2030, 11, 1)
    assert cycle_range(date(2030, 10, 1), 5) == (date(2030, 10, 5), date(2030, 11, 4))
    assert cycle_range(date(2030, 10, 1)) == (date(2030, 10, 1), date(2030, 10, 31))
    assert cycle_date(date(2030, 10, 1), 2, 5) == date(2030, 11, 2)
    assert cycle_date(date(2030, 10, 1), 20, 5) == date(2030, 10, 20)
    # Fevereiro mais curto: o fim do ciclo de janeiro respeita o mês.
    assert cycle_range(date(2031, 1, 1), 28)[1] == date(2031, 2, 27)
    assert current_month(1) == current_month()


def test_cycle_setting_and_recurring_due_dates(user: TestClient, db: Session) -> None:
    assert user.get("/api/auth/me").json()["month_start_day"] == 1
    assert user.patch("/api/me/cycle", json={"month_start_day": 31}).status_code == 422
    assert user.patch("/api/me/cycle", json={"month_start_day": 5}).json() == {"month_start_day": 5}
    assert user.get("/api/auth/me").json()["month_start_day"] == 5
    # Conta fixa com vencimento no dia 2: no ciclo de fevereiro (5/2 a 4/3) ela vence em 2/3.
    user.post(
        "/api/recurring",
        json={
            "kind": "expense",
            "description": "Internet",
            "amount": "99.90",
            "due_day": 2,
            "start_month": "2030-02",
        },
    )
    month = user.get("/api/months/2030-02").json()
    [internet] = [e for e in month["expenses"] if e["description"] == "Internet"]
    assert internet["due_date"] == "2030-03-02"


def test_forecast_follows_the_cycle(user: TestClient, db: Session) -> None:
    user.patch("/api/me/cycle", json={"month_start_day": 5})
    user.post(
        "/api/months/2030-02/incomes",
        json={"description": "Salário", "amount": "3000.00", "day": 5},
    )
    expense(user, "2030-02", description="Aluguel", amount="1000.00", due_date="2030-03-03")
    data = daily.forecast(db, me(db), date(2030, 2, 1), today=date(2030, 2, 10))
    days = data["days"]
    assert days[0]["date"] == date(2030, 2, 5) and days[-1]["date"] == date(2030, 3, 4)
    assert len(days) == 28
    # O aluguel (3/3) cai no fim do ciclo, não no começo.
    by_day = {d["date"]: d["balance"] for d in days}
    assert by_day[date(2030, 3, 2)] == Decimal("3000.00")
    assert by_day[date(2030, 3, 3)] == Decimal("2000.00")


def test_monthly_summary_on_cycle_start(db: Session, user: TestClient, outbox) -> None:
    user.patch("/api/me/cycle", json={"month_start_day": 5})
    user.post("/api/months/2030-01/incomes", json={"description": "Salário", "amount": "3000"})
    expense(user, "2030-01", description="Mercado", amount="500.00", paid=True)
    sent = len(outbox)
    notify.run_daily(db, datetime(2030, 2, 1, 9, tzinfo=TZ))
    assert not [m for m in outbox[sent:] if "resumo" in m.subject.lower()]
    notify.run_daily(db, datetime(2030, 2, 5, 9, tzinfo=TZ))
    summaries = [m for m in outbox[sent:] if "resumo" in m.subject.lower()]
    assert len(summaries) == 1 and "janeiro" in summaries[0].subject.lower()


# ---------------------------------------------------------------- alertas


def test_unusual_and_new_merchant_alerts(user: TestClient, db: Session) -> None:
    cats = {c["name"]: c["id"] for c in user.get("/api/categories").json()}
    for month in ("2029-10", "2029-11", "2029-12"):
        expense(user, month, description="Restaurante", amount="80.00", category_id=cats["Lazer"])
    expense(user, "2029-12", description="Restaurante", amount="70.00", category_id=cats["Lazer"])
    expense(
        user,
        "2030-01",
        description="Jantar de aniversário",
        amount="450.00",
        category_id=cats["Lazer"],
    )
    expense(
        user,
        "2030-01",
        description="Loja Desconhecida XYZ",
        amount="320.00",
        category_id=cats["Compras"],
    )
    expense(user, "2030-01", description="Restaurante", amount="90.00", category_id=cats["Lazer"])
    kinds = {a["kind"]: a for a in user.get("/api/alerts?month=2030-01").json()}
    assert "Jantar de aniversário" in kinds["unusual"]["title"]
    assert "Loja Desconhecida XYZ" in kinds["new_merchant"]["title"]
    assert len(user.get("/api/alerts?month=2030-01").json()) == 2


def test_price_up_only_for_subscriptions(user: TestClient) -> None:
    for month in ("2029-10", "2029-11", "2029-12"):
        expense(user, month, description="Streaming Plus", amount="39.90")
        expense(user, month, description="Mercado", amount="300.00")
        expense(user, month, description="Mercado", amount="250.00")
    expense(user, "2030-01", description="Streaming Plus", amount="44.90")
    expense(user, "2030-01", description="Mercado", amount="600.00")
    titles = [
        a["title"] for a in user.get("/api/alerts?month=2030-01").json() if a["kind"] == "price_up"
    ]
    assert titles == ["Ficou mais caro: Streaming Plus"]


def test_annual_renewal_alert(user: TestClient, db: Session) -> None:
    user.post(
        "/api/recurring",
        json={
            "kind": "expense",
            "description": "Antivírus anual",
            "amount": "199.00",
            "due_day": 15,
            "start_month": "2029-01",
            "interval_months": 12,
        },
    )
    found = alerts.month_alerts(db, me(db), date(2030, 1, 1), today=date(2030, 1, 10))
    assert [a["kind"] for a in found] == ["renewal"]
    assert alerts.month_alerts(db, me(db), date(2030, 1, 1), today=date(2030, 1, 1)) == []


def test_daily_alerts_go_to_inbox_once(user: TestClient, db: Session, outbox) -> None:
    for month in ("2029-10", "2029-11", "2029-12"):
        expense(user, month, description="Padaria", amount="20.00")
    expense(user, "2030-01", description="Loja de eletrônicos", amount="1500.00")
    mails: list[str] = []

    def mail(to: str, subject: str, body: str, html=None, headers=None) -> None:  # type: ignore[no-untyped-def]
        mails.append(subject)

    import app.services.alerts as alerts_module

    original = alerts_module.month_of
    alerts_module.month_of = lambda *_: date(2030, 1, 1)  # type: ignore[assignment]
    try:
        assert alerts.run_daily(db, mail, today=date(2030, 1, 20)) == 1
        assert alerts.run_daily(db, mail, today=date(2030, 1, 20)) == 0
    finally:
        alerts_module.month_of = original  # type: ignore[assignment]
    assert len(mails) == 1
    items = list(db.scalars(select(InboxItem).where(InboxItem.kind == "alert")))
    assert len(items) == 1 and "Loja de eletrônicos" in items[0].title
    assert db.scalar(select(func.count()).select_from(NotificationLog)) == 1
    [row] = user.get("/api/inbox").json()
    assert row["kind"] == "alert"
    # Alertas por e-mail podem ser desligados (a caixa continua recebendo).
    user.patch("/api/notifications/prefs", json={"notify_alerts": False})
    assert me(db).notify_alerts is False


# ---------------------------------------------------------------- divisões


def test_split_equal_amount_and_percent(user: TestClient) -> None:
    dinner = expense(user, "2030-01", description="Jantar", amount="300.00")
    out = user.put(
        f"/api/expenses/{dinner['id']}/split",
        json={"people": [{"person": "Bia"}, {"person": "Caio"}], "mode": "equal"},
    )
    assert out.status_code == 200, out.text
    assert sorted((s["person"], s["amount"]) for s in out.json()) == [
        ("Bia", "100.00"),
        ("Caio", "100.00"),
    ]
    # Dividir de novo substitui a divisão anterior.
    again = user.put(
        f"/api/expenses/{dinner['id']}/split",
        json={"people": [{"person": "Bia", "value": "40"}], "mode": "percent"},
    ).json()
    assert [(s["person"], s["amount"]) for s in again] == [("Bia", "120.00")]
    trip = expense(user, "2030-01", description="Gasolina", amount="200.00")
    user.put(
        f"/api/expenses/{trip['id']}/split",
        json={"people": [{"person": "bia", "value": "50.00"}], "mode": "amount"},
    )
    too_much = user.put(
        f"/api/expenses/{trip['id']}/split",
        json={"people": [{"person": "Bia", "value": "250.00"}], "mode": "amount"},
    )
    assert too_much.status_code == 400
    dup = user.put(
        f"/api/expenses/{trip['id']}/split",
        json={"people": [{"person": "Bia"}, {"person": " bia "}], "mode": "equal"},
    )
    assert dup.status_code == 400
    board = user.get("/api/splits").json()
    [bia] = board["people"]
    # O mesmo nome com outra caixa conta como a mesma pessoa.
    assert bia["balance"] == "170.00" and len(bia["items"]) == 2
    assert board["owed_to_me"] == "170.00"


def test_board_both_directions_and_settle(user: TestClient, db: Session) -> None:
    user.post(
        "/api/splits",
        json={
            "person": "Caio",
            "description": "Ingresso do show",
            "amount": "120.00",
            "direction": "owes_me",
        },
    )
    user.post(
        "/api/splits",
        json={"person": "Caio", "description": "Uber", "amount": "30.00", "direction": "i_owe"},
    )
    user.post(
        "/api/splits",
        json={"person": "Duda", "description": "Presente", "amount": "50.00", "direction": "i_owe"},
    )
    board = user.get("/api/splits").json()
    balances = {p["person"]: p["balance"] for p in board["people"]}
    assert balances == {"Caio": "90.00", "Duda": "-50.00"}
    assert board["owed_to_me"] == "90.00" and board["i_owe"] == "50.00"
    settled = user.post("/api/splits/settle", json={"person": "caio", "record_income": True}).json()
    assert settled["balance"] == "90.00" and settled["income_id"]
    db.expire_all()
    income = db.get(Income, uuid.UUID(settled["income_id"]))
    assert income is not None and income.description == "Reembolso de Caio"
    assert income.amount == Decimal("90.00") and income.month == date(2030, 1, 1)
    board = user.get("/api/splits").json()
    assert [p["person"] for p in board["people"]] == ["Duda"] and len(board["history"]) == 2
    # Quando o saldo é do usuário para a pessoa, nada vira receita.
    out = user.post("/api/splits/settle", json={"person": "Duda", "record_income": True}).json()
    assert out["income_id"] is None
    assert user.post("/api/splits/settle", json={"person": "Duda"}).status_code == 404


def test_splits_are_private(client: TestClient, outbox: list[OutgoingEmail]) -> None:
    create_verified_user(client, outbox, "ana@example.com")
    login(client, "ana@example.com")
    dinner = expense(client, "2030-01", description="Jantar", amount="100.00")
    share = client.post(
        "/api/splits",
        json={"person": "Bia", "amount": "10.00", "direction": "owes_me"},
    ).json()
    client.post("/api/auth/logout")
    create_verified_user(client, outbox, "bia@example.com")
    login(client, "bia@example.com")
    assert client.get("/api/splits").json()["people"] == []
    assert client.delete(f"/api/splits/{share['id']}").status_code == 404
    split = client.put(f"/api/expenses/{dinner['id']}/split", json={"people": [{"person": "X"}]})
    assert split.status_code == 404
