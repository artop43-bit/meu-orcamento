import time
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.cli import cleanup
from app.core.email import OutgoingEmail
from app.db.types import utcnow
from app.models import AuthToken, Expense, Goal, SecurityEvent, User, UserSession
from tests.conftest import PASSWORD, create_verified_user, enable_2fa, login

Outbox = list[OutgoingEmail]


# ---------------------------------------------------------------- termos (LGPD)


def test_register_requires_accepting_terms(client: TestClient, outbox: Outbox) -> None:
    for payload in (
        {"email": "ana@example.com", "password": PASSWORD},
        {"email": "ana@example.com", "password": PASSWORD, "accept_terms": False},
    ):
        response = client.post("/api/auth/register", json=payload)
        assert response.status_code == 422
        assert "Termos de uso" in response.json()["message"]
    assert outbox == []


def test_terms_acceptance_is_recorded(client: TestClient, outbox: Outbox, db: Session) -> None:
    create_verified_user(client, outbox)
    user = db.scalars(select(User)).one()
    assert user.terms_accepted_at is not None
    assert user.terms_version == "2026-10-16"


# ---------------------------------------------------------------- limite por IP


def test_login_rate_limit_per_ip(client: TestClient) -> None:
    for _ in range(20):
        client.post("/api/auth/login", json={"email": "x@example.com", "password": "errada"})
    response = client.post("/api/auth/login", json={"email": "y@example.com", "password": "x"})
    assert response.status_code == 429
    assert response.json()["error"] == "rate_limited"
    assert int(response.headers["Retry-After"]) > 0


def test_signup_rate_limit(client: TestClient) -> None:
    for i in range(10):
        response = client.post(
            "/api/auth/register",
            json={"email": f"p{i}@example.com", "password": PASSWORD, "accept_terms": True},
        )
        assert response.status_code == 202
    blocked = client.post(
        "/api/auth/register",
        json={"email": "outra@example.com", "password": PASSWORD, "accept_terms": True},
    )
    assert blocked.status_code == 429


# ---------------------------------------------------------------- cabeçalhos


def test_security_headers(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Cache-Control"] == "no-store"
    # HSTS só em produção (HTTPS).
    assert "Strict-Transport-Security" not in response.headers


# ---------------------------------------------------------------- eventos e sessões


def test_security_events(client: TestClient, outbox: Outbox) -> None:
    create_verified_user(client, outbox)
    login(client, password="senha-errada-000")
    login(client)
    client.post(
        "/api/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "nova-senha-456"},
    )

    events = client.get("/api/auth/events").json()
    assert [e["event"] for e in events] == [
        "password_changed",
        "login",
        "login_failed",
        "email_verified",
    ]
    assert events[0]["ip"] == "testclient"


def test_list_and_revoke_sessions(client: TestClient, outbox: Outbox, db: Session) -> None:
    create_verified_user(client, outbox)
    login(client)  # sessão "antiga"
    old_cookie = client.cookies.get("session")
    login(client)  # sessão atual

    sessions = client.get("/api/auth/sessions").json()
    assert len(sessions) == 2
    current = next(s for s in sessions if s["current"])
    other = next(s for s in sessions if not s["current"])

    # Não dá para encerrar a própria sessão por aqui.
    assert client.delete(f"/api/auth/sessions/{current['id']}").status_code == 400

    assert client.delete(f"/api/auth/sessions/{other['id']}").status_code == 204
    assert len(client.get("/api/auth/sessions").json()) == 1

    # O cookie da sessão encerrada não vale mais.
    client.cookies.set("session", old_cookie)
    assert client.get("/api/auth/me").status_code == 401


def test_revoke_other_sessions(client: TestClient, outbox: Outbox) -> None:
    create_verified_user(client, outbox)
    for _ in range(3):
        login(client)
    assert client.post("/api/auth/sessions/revoke-others").status_code == 204
    sessions = client.get("/api/auth/sessions").json()
    assert len(sessions) == 1 and sessions[0]["current"]


def test_cannot_revoke_someone_elses_session(client: TestClient, outbox: Outbox) -> None:
    create_verified_user(client, outbox, "ana@example.com")
    create_verified_user(client, outbox, "bia@example.com")
    login(client, "ana@example.com")
    ana_session = client.get("/api/auth/sessions").json()[0]["id"]
    client.post("/api/auth/logout")

    login(client, "bia@example.com")
    assert client.delete(f"/api/auth/sessions/{ana_session}").status_code == 404


# ---------------------------------------------------------------- exclusão de conta


def test_delete_account_removes_everything(client: TestClient, outbox: Outbox, db: Session) -> None:
    create_verified_user(client, outbox)
    login(client)
    client.post("/api/months/2030-01/expenses", json={"description": "X", "amount": "10"})
    client.post("/api/goals", json={"name": "Meta", "target_amount": "100"})

    wrong = client.post("/api/auth/delete-account", json={"password": "errada-123"})
    assert wrong.status_code == 400

    response = client.post("/api/auth/delete-account", json={"password": PASSWORD})
    assert response.status_code == 204
    assert outbox[-1].subject == "Sua conta foi excluída"

    assert client.get("/api/auth/me").status_code == 401
    assert login(client).status_code == 401
    for model in (User, Expense, Goal, UserSession, SecurityEvent, AuthToken):
        assert db.scalar(select(func.count()).select_from(model)) == 0, model.__name__


def test_delete_account_with_2fa_requires_code(client: TestClient, outbox: Outbox) -> None:
    create_verified_user(client, outbox)
    login(client)
    otp, _ = enable_2fa(client)

    response = client.post("/api/auth/delete-account", json={"password": PASSWORD})
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_code"

    code = otp.at(time.time() + 30)
    response = client.post("/api/auth/delete-account", json={"password": PASSWORD, "code": code})
    assert response.status_code == 204


def test_delete_account_keeps_other_users(client: TestClient, outbox: Outbox, db: Session) -> None:
    create_verified_user(client, outbox, "ana@example.com")
    create_verified_user(client, outbox, "bia@example.com")
    login(client, "ana@example.com")
    client.post("/api/auth/delete-account", json={"password": PASSWORD})

    assert [u.email for u in db.scalars(select(User))] == ["bia@example.com"]
    assert login(client, "bia@example.com").status_code == 200


# ---------------------------------------------------------------- limpeza


def test_cleanup(client: TestClient, outbox: Outbox, db: Session) -> None:
    create_verified_user(client, outbox)
    login(client)
    login(client)
    user = db.scalars(select(User)).one()
    now = utcnow()

    expired = db.scalars(select(UserSession)).first()
    assert expired is not None
    expired.expires_at = now - timedelta(seconds=1)
    for token in db.scalars(select(AuthToken)):
        token.used_at = now - timedelta(days=8)
    db.add(SecurityEvent(user_id=user.id, event="login", created_at=now - timedelta(days=200)))
    db.commit()

    removed = cleanup(db)
    assert removed["sessions"] == 1
    assert removed["tokens"] >= 1
    assert removed["security_events"] == 1
    # A sessão ainda válida continua funcionando.
    assert client.get("/api/auth/me").status_code == 200
