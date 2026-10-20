from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.email import OutgoingEmail
from app.services import budget as budget_service
from app.services import money
from tests.conftest import PASSWORD, create_verified_user, login, token_from

MONTH = "2030-01"


@pytest.fixture
def user(client: TestClient, outbox: list[OutgoingEmail]) -> TestClient:
    create_verified_user(client, outbox)
    login(client)
    return client


@pytest.fixture(autouse=True)
def fixed_current_month(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(budget_service, "current_month", lambda *_: date(2030, 1, 1))


def add_expense(client: TestClient, month: str = MONTH, **data: Any) -> list[dict[str, Any]]:
    payload = {"description": "Conta", "amount": "100.00", **data}
    response = client.post(f"/api/months/{month}/expenses", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def category_id(client: TestClient, name: str) -> str:
    return next(c["id"] for c in client.get("/api/categories").json() if c["name"] == name)


# ---------------------------------------------------------------- limite de datas


@pytest.mark.parametrize("value", ["888888-08-08", "1999-12-31", "2101-01-01"])
def test_unrealistic_dates_are_rejected(user: TestClient, value: str) -> None:
    response = user.post(
        f"/api/months/{MONTH}/expenses",
        json={"description": "X", "amount": "1.00", "due_date": value},
    )
    assert response.status_code == 422
    assert "Data inválida" in response.json()["message"]


def test_unrealistic_months_are_rejected(user: TestClient) -> None:
    assert user.get("/api/months/1990-01").status_code == 400
    response = user.post(
        "/api/recurring",
        json={"kind": "expense", "description": "X", "amount": "1.00", "start_month": "2999-01"},
    )
    assert response.status_code == 422


def test_new_default_categories(user: TestClient) -> None:
    names = {c["name"] for c in user.get("/api/categories").json()}
    assert {"Compras", "Assinaturas", "Pets"} <= names


# ---------------------------------------------------------------- beta fechado e admin


def test_signup_waits_for_approval(
    client: TestClient, outbox: list[OutgoingEmail], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "signup_approval", True)
    monkeypatch.setattr(get_settings(), "admin_emails", "chefe@example.com")
    create_verified_user(client, outbox, "chefe@example.com")
    create_verified_user(client, outbox, "nova@example.com")
    blocked = client.post(
        "/api/auth/login", json={"email": "nova@example.com", "password": PASSWORD}
    )
    assert blocked.status_code == 403
    assert blocked.json()["error"] == "access_pending"

    # O admin entra (ADMIN_EMAILS é liberado na hora), vê o cadastro pendente e libera.
    login(client, "chefe@example.com")
    overview = client.get("/api/admin/overview").json()
    assert overview["pending"] == 1
    users = {u["email"]: u for u in client.get("/api/admin/users").json()}
    assert users["nova@example.com"]["access_status"] == "pending"
    assert users["chefe@example.com"]["is_admin"] is True
    # Os e-mails de confirmação ficam no painel, com o link.
    emails = client.get("/api/admin/emails").json()
    confirm = [e for e in emails if e["to"] == "nova@example.com" and "Confirme" in e["subject"]]
    assert confirm and confirm[0]["link"].startswith("http://web.local/verificar-email?token=")
    response = client.post(
        f"/api/admin/users/{users['nova@example.com']['id']}/action", json={"action": "approve"}
    )
    assert response.json() == {"status": "approved"}
    assert any("Acesso liberado" in m.subject for m in outbox if m.to == "nova@example.com")

    client.post("/api/auth/logout")
    assert login(client, "nova@example.com").status_code == 200


def test_admin_actions_and_protection(
    client: TestClient, outbox: list[OutgoingEmail], monkeypatch: pytest.MonkeyPatch
) -> None:
    create_verified_user(client, outbox, "ana@example.com")
    create_verified_user(client, outbox, "bia@example.com")
    login(client, "bia@example.com")
    assert client.get("/api/admin/users").status_code == 403

    monkeypatch.setattr(get_settings(), "admin_emails", "ana@example.com")
    client.post("/api/auth/logout")
    login(client, "ana@example.com")
    users = {u["email"]: u["id"] for u in client.get("/api/admin/users").json()}
    me, bia = users["ana@example.com"], users["bia@example.com"]
    # Não pode bloquear a si mesmo.
    assert client.post(f"/api/admin/users/{me}/action", json={"action": "block"}).status_code == 400
    assert client.post(f"/api/admin/users/{bia}/action", json={"action": "block"}).json() == {
        "status": "blocked"
    }
    client.post("/api/auth/logout")
    blocked = client.post(
        "/api/auth/login", json={"email": "bia@example.com", "password": PASSWORD}
    )
    assert blocked.json()["error"] == "access_blocked"
    login(client, "ana@example.com")
    client.post(f"/api/admin/users/{bia}/action", json={"action": "unblock"})
    client.post(f"/api/admin/users/{bia}/action", json={"action": "make_admin"})
    assert {u["email"]: u["is_admin"] for u in client.get("/api/admin/users").json()}[
        "bia@example.com"
    ]
    assert client.post(f"/api/admin/users/{bia}/action", json={"action": "delete"}).json() == {
        "status": "deleted"
    }
    assert "bia@example.com" not in {u["email"] for u in client.get("/api/admin/users").json()}


def test_resend_and_verify_from_panel(
    client: TestClient, outbox: list[OutgoingEmail], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "admin_emails", "ana@example.com")
    create_verified_user(client, outbox, "ana@example.com")
    client.post(
        "/api/auth/register",
        json={"email": "lia@example.com", "password": PASSWORD, "accept_terms": True},
    )
    login(client, "ana@example.com")
    lia = next(u for u in client.get("/api/admin/users").json() if u["email"] == "lia@example.com")
    assert lia["email_verified"] is False
    before = len([m for m in outbox if m.to == "lia@example.com"])
    client.post(f"/api/admin/users/{lia['id']}/action", json={"action": "resend_verification"})
    assert len([m for m in outbox if m.to == "lia@example.com"]) == before + 1
    assert token_from(outbox[-1])
    client.post(f"/api/admin/users/{lia['id']}/action", json={"action": "verify_email"})
    lia = next(u for u in client.get("/api/admin/users").json() if u["email"] == "lia@example.com")
    assert lia["email_verified"] is True


# ---------------------------------------------------------------- contas e saldos


def test_accounts_balances_and_transfers(user: TestClient, db: Any) -> None:
    conta = user.post(
        "/api/accounts", json={"name": "Nubank", "kind": "checking", "initial_balance": "1000.00"}
    ).json()
    cofre = user.post("/api/accounts", json={"name": "Poupança", "kind": "savings"}).json()
    user.post(
        f"/api/months/{MONTH}/incomes",
        json={"description": "Salário", "amount": "3000.00", "day": 5, "account_id": conta["id"]},
    )
    add_expense(user, amount="200.00", paid=True, account_id=conta["id"], due_date="2030-01-03")
    add_expense(user, amount="50.00", account_id=conta["id"], due_date="2030-01-28")
    user.post(
        "/api/transfers",
        json={
            "from_account_id": conta["id"],
            "to_account_id": cofre["id"],
            "amount": "500.00",
            "date": "2030-01-10",
        },
    )
    data = {b["account"].name: b for b in money.balances(db, _user(db), date(2030, 1, 20))}
    assert data["Nubank"]["balance"] == 1000 + 3000 - 200 - 500
    assert data["Nubank"]["end_of_month"] == 1000 + 3000 - 200 - 500 - 50
    assert data["Poupança"]["balance"] == 500
    same = user.post(
        "/api/transfers",
        json={
            "from_account_id": conta["id"],
            "to_account_id": conta["id"],
            "amount": "1.00",
            "date": "2030-01-10",
        },
    )
    assert same.status_code == 400


def _user(db: Any) -> Any:
    from sqlalchemy import select

    from app.models import User

    return db.scalar(select(User).where(User.email == "ana@example.com"))


def test_account_belongs_to_owner(user: TestClient, outbox: list[OutgoingEmail]) -> None:
    conta = user.post("/api/accounts", json={"name": "Nubank"}).json()
    user.post("/api/auth/logout")
    create_verified_user(user, outbox, "bia@example.com")
    login(user, "bia@example.com")
    response = user.post(
        f"/api/months/{MONTH}/expenses",
        json={"description": "X", "amount": "1.00", "account_id": conta["id"]},
    )
    assert response.status_code == 404
    assert user.get("/api/accounts").json() == []


# ---------------------------------------------------------------- revisar, busca, ritmo, copiar


def test_review_queue(user: TestClient, db: Any) -> None:
    [a] = add_expense(user, description="PAG*LOJA X")
    [b] = add_expense(user, description="UBER *TRIP")
    from sqlalchemy import update

    from app.models import Expense

    db.execute(update(Expense).values(needs_review=True))
    db.commit()
    queue = user.get("/api/review").json()
    assert {e["id"] for e in queue} == {a["id"], b["id"]}
    transporte = category_id(user, "Transporte")
    compras = category_id(user, "Compras")
    response = user.post(
        "/api/review/confirm",
        json={"ids": [a["id"], b["id"]], "categories": {a["id"]: compras, b["id"]: transporte}},
    )
    assert response.json() == {"count": 2}
    assert user.get("/api/review").json() == []
    cats = {
        e["description"]: e["category_id"]
        for e in user.get(f"/api/months/{MONTH}").json()["expenses"]
    }
    assert cats == {"PAG*LOJA X": compras, "UBER *TRIP": transporte}


def test_search_all_months(user: TestClient) -> None:
    add_expense(
        user, "2029-11", description="Farmácia São João", amount="42.00", payment_method="pix"
    )
    add_expense(user, "2030-01", description="Farmacia Popular", amount="18.00")
    add_expense(user, "2030-01", description="Mercado", amount="300.00")
    user.post(f"/api/months/{MONTH}/incomes", json={"description": "Salário", "amount": "3000.00"})
    data = user.get("/api/search", params={"q": "farmácia"}).json()
    assert data["count"] == 2
    assert [r["month"] for r in data["results"]] == ["2030-01", "2029-11"]
    assert data["total_expenses"] == "60.00"
    assert user.get("/api/search", params={"min_amount": 100}).json()["count"] == 2
    assert user.get("/api/search", params={"payment_method": "pix"}).json()["count"] == 1
    assert (
        user.get("/api/search", params={"kind": "income"}).json()["results"][0]["description"]
        == "Salário"
    )
    assert user.get("/api/search", params={"start": "2030-01-01", "q": "farm"}).json()["count"] == 1


def test_pace_by_category(user: TestClient, db: Any) -> None:
    lazer = category_id(user, "Lazer")
    user.patch(f"/api/categories/{lazer}", json={"monthly_limit": "300.00"})
    add_expense(user, description="Cinema", amount="200.00", category_id=lazer)
    rows = {r["name"]: r for r in money.pace(db, _user(db), date(2030, 1, 1), date(2030, 1, 10))}
    assert rows["Lazer"]["status"] == "risk"
    assert rows["Lazer"]["reference_kind"] == "limit"
    add_expense(user, description="Show", amount="150.00", category_id=lazer)
    rows = {r["name"]: r for r in money.pace(db, _user(db), date(2030, 1, 1), date(2030, 1, 10))}
    assert rows["Lazer"]["status"] == "over"


def test_copy_previous_month(user: TestClient) -> None:
    add_expense(
        user, "2029-12", description="Feira", amount="80.00", due_date="2029-12-06", paid=True
    )
    add_expense(user, "2029-12", description="TV", installments=2)
    user.post(
        "/api/recurring",
        json={
            "kind": "expense",
            "description": "Internet",
            "amount": "99.00",
            "start_month": "2029-12",
        },
    )
    user.get("/api/months/2029-12")
    candidates = user.get(f"/api/months/{MONTH}/copy-candidates").json()
    assert [c["description"] for c in candidates] == ["Feira"]
    created = user.post(
        f"/api/months/{MONTH}/copy-previous", json={"ids": [candidates[0]["id"]]}
    ).json()
    assert (created[0]["due_date"], created[0]["paid"], created[0]["month"]) == (
        "2030-01-06",
        False,
        MONTH,
    )
