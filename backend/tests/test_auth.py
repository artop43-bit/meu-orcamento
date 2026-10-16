import time
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.email import OutgoingEmail
from app.db.types import utcnow
from app.models import AuthToken, User
from tests.conftest import PASSWORD, create_verified_user, enable_2fa, login, token_from

Outbox = list[OutgoingEmail]


# ---------------------------------------------------------------- cadastro e verificação


def test_register_verify_and_login(client: TestClient, outbox: Outbox) -> None:
    response = client.post(
        "/api/auth/register", json={"email": " Ana@Example.com ", "password": PASSWORD}
    )
    assert response.status_code == 202
    assert len(outbox) == 1
    assert outbox[0].to == "ana@example.com"
    assert "http://web.local/verificar-email?token=" in outbox[0].body

    # Não entra antes de confirmar o e-mail.
    assert login(client).status_code == 403

    token = token_from(outbox[0])
    assert client.post("/api/auth/verify-email", json={"token": token}).status_code == 200
    # O link é de uso único.
    assert client.post("/api/auth/verify-email", json={"token": token}).status_code == 400

    response = login(client, address="ANA@example.com")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.cookies.get("session")

    me = client.get("/api/auth/me").json()
    assert me["email"] == "ana@example.com"
    assert me["email_verified"] is True
    assert me["totp_enabled"] is False


def test_register_existing_email_does_not_reveal_it(
    client: TestClient, outbox: Outbox, db: Session
) -> None:
    create_verified_user(client, outbox)
    outbox.clear()

    response = client.post(
        "/api/auth/register", json={"email": "ana@example.com", "password": "outra-senha-123"}
    )
    assert response.status_code == 202
    assert "já está cadastrado" in outbox[0].body
    assert len(db.scalars(select(User)).all()) == 1
    # A senha original continua valendo.
    assert login(client).status_code == 200


def test_resend_verification_invalidates_previous_link(client: TestClient, outbox: Outbox) -> None:
    client.post("/api/auth/register", json={"email": "ana@example.com", "password": PASSWORD})
    old = token_from(outbox[-1])
    client.post("/api/auth/resend-verification", json={"email": "ana@example.com"})
    new = token_from(outbox[-1])

    assert client.post("/api/auth/verify-email", json={"token": old}).status_code == 400
    assert client.post("/api/auth/verify-email", json={"token": new}).status_code == 200


def test_short_password_is_rejected_with_friendly_message(client: TestClient) -> None:
    response = client.post(
        "/api/auth/register", json={"email": "ana@example.com", "password": "curta"}
    )
    assert response.status_code == 422
    assert response.json()["message"] == "A senha precisa ter pelo menos 10 caracteres."


# ---------------------------------------------------------------- login e sessão


def test_wrong_password_and_lockout(client: TestClient, outbox: Outbox) -> None:
    create_verified_user(client, outbox)

    for _ in range(5):
        response = login(client, password="senha-errada-000")
        assert response.status_code in (401, 429)

    # Bloqueada: nem a senha certa entra.
    response = login(client)
    assert response.status_code == 429
    assert response.json()["error"] == "account_locked"


def test_lockout_expires(client: TestClient, outbox: Outbox, db: Session) -> None:
    create_verified_user(client, outbox)
    for _ in range(5):
        login(client, password="senha-errada-000")

    user = db.scalars(select(User)).one()
    user.locked_until = utcnow() - timedelta(seconds=1)
    db.commit()

    assert login(client).status_code == 200


def test_unknown_email_gets_same_error_as_wrong_password(client: TestClient) -> None:
    response = login(client, address="ninguem@example.com")
    assert response.status_code == 401
    assert response.json()["error"] == "invalid_credentials"


def test_logout_ends_session(client: TestClient, outbox: Outbox) -> None:
    create_verified_user(client, outbox)
    login(client)
    assert client.get("/api/auth/me").status_code == 200

    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_post_without_csrf_header_is_blocked(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": "ana@example.com", "password": PASSWORD},
        headers={"X-Requested-With": ""},
    )
    assert response.status_code == 403
    assert response.json()["error"] == "csrf"


# ---------------------------------------------------------------- recuperação de senha


def test_forgot_password_unknown_email_sends_nothing(client: TestClient, outbox: Outbox) -> None:
    response = client.post("/api/auth/forgot-password", json={"email": "ninguem@example.com"})
    assert response.status_code == 202
    assert outbox == []


def test_reset_password_flow(client: TestClient, outbox: Outbox) -> None:
    create_verified_user(client, outbox)
    login(client)
    assert client.get("/api/auth/me").status_code == 200

    client.post("/api/auth/forgot-password", json={"email": "ana@example.com"})
    token = token_from(outbox[-1])
    assert "/redefinir-senha?token=" in outbox[-1].body

    new_password = "nova-senha-456"
    response = client.post(
        "/api/auth/reset-password", json={"token": token, "password": new_password}
    )
    assert response.status_code == 200
    assert outbox[-1].subject == "Sua senha foi alterada"

    # Todas as sessões foram encerradas.
    assert client.get("/api/auth/me").status_code == 401
    assert login(client).status_code == 401
    assert login(client, password=new_password).status_code == 200

    # O link não pode ser reutilizado.
    response = client.post(
        "/api/auth/reset-password", json={"token": token, "password": "mais-uma-senha-789"}
    )
    assert response.status_code == 400


def test_expired_reset_link_is_rejected(client: TestClient, outbox: Outbox, db: Session) -> None:
    create_verified_user(client, outbox)
    client.post("/api/auth/forgot-password", json={"email": "ana@example.com"})
    token = token_from(outbox[-1])

    for row in db.scalars(select(AuthToken)).all():
        row.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()

    response = client.post(
        "/api/auth/reset-password", json={"token": token, "password": "nova-senha-456"}
    )
    assert response.status_code == 400


def test_change_password_keeps_current_session(client: TestClient, outbox: Outbox) -> None:
    create_verified_user(client, outbox)
    login(client)

    response = client.post(
        "/api/auth/change-password",
        json={"current_password": "errada-123", "new_password": "nova-senha-456"},
    )
    assert response.status_code == 400

    response = client.post(
        "/api/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "nova-senha-456"},
    )
    assert response.status_code == 204
    assert client.get("/api/auth/me").status_code == 200
    assert login(client, password="nova-senha-456").status_code == 200


# ---------------------------------------------------------------- 2FA


def test_2fa_login_flow(client: TestClient, outbox: Outbox) -> None:
    create_verified_user(client, outbox)
    login(client)
    otp, recovery_codes = enable_2fa(client)
    assert len(recovery_codes) == 10
    assert client.get("/api/auth/me").json()["totp_enabled"] is True

    client.post("/api/auth/logout")

    response = login(client)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "2fa_required"
    assert "session" not in response.cookies
    challenge = body["challenge"]

    # Senha certa não basta.
    assert client.get("/api/auth/me").status_code == 401

    bad = client.post("/api/auth/login/2fa", json={"challenge": challenge, "code": "000000"})
    assert bad.status_code == 400

    # Próximo código (o atual já foi usado na ativação).
    code = otp.at(time.time() + 30)
    ok = client.post("/api/auth/login/2fa", json={"challenge": challenge, "code": code})
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "ok"
    assert client.get("/api/auth/me").status_code == 200

    # O desafio é de uso único.
    again = client.post("/api/auth/login/2fa", json={"challenge": challenge, "code": code})
    assert again.status_code == 400


def test_2fa_code_cannot_be_replayed(client: TestClient, outbox: Outbox) -> None:
    create_verified_user(client, outbox)
    login(client)
    otp, _ = enable_2fa(client)
    client.post("/api/auth/logout")

    code = otp.at(time.time() + 30)
    first = login(client).json()["challenge"]
    assert (
        client.post("/api/auth/login/2fa", json={"challenge": first, "code": code}).status_code
        == 200
    )

    client.post("/api/auth/logout")
    second = login(client).json()["challenge"]
    replay = client.post("/api/auth/login/2fa", json={"challenge": second, "code": code})
    assert replay.status_code == 400


def test_recovery_code_works_once(client: TestClient, outbox: Outbox) -> None:
    create_verified_user(client, outbox)
    login(client)
    _, codes = enable_2fa(client)
    client.post("/api/auth/logout")

    challenge = login(client).json()["challenge"]
    used = codes[0].upper()  # aceita maiúsculas
    ok = client.post("/api/auth/login/2fa", json={"challenge": challenge, "code": used})
    assert ok.status_code == 200
    assert client.get("/api/auth/2fa").json()["recovery_codes_remaining"] == 9

    client.post("/api/auth/logout")
    challenge = login(client).json()["challenge"]
    reused = client.post("/api/auth/login/2fa", json={"challenge": challenge, "code": used})
    assert reused.status_code == 400


def test_2fa_brute_force_locks_account(client: TestClient, outbox: Outbox) -> None:
    create_verified_user(client, outbox)
    login(client)
    enable_2fa(client)
    client.post("/api/auth/logout")

    challenge = login(client).json()["challenge"]
    for _ in range(5):
        client.post("/api/auth/login/2fa", json={"challenge": challenge, "code": "000000"})

    response = client.post("/api/auth/login/2fa", json={"challenge": challenge, "code": "111111"})
    assert response.status_code == 429


def test_disable_2fa_requires_password_and_code(client: TestClient, outbox: Outbox) -> None:
    create_verified_user(client, outbox)
    login(client)
    otp, _ = enable_2fa(client)
    code = otp.at(time.time() + 30)

    wrong_password = client.post(
        "/api/auth/2fa/disable", json={"password": "errada-123", "code": code}
    )
    assert wrong_password.status_code == 400

    response = client.post("/api/auth/2fa/disable", json={"password": PASSWORD, "code": code})
    assert response.status_code == 204
    assert client.get("/api/auth/me").json()["totp_enabled"] is False

    client.post("/api/auth/logout")
    assert login(client).json()["status"] == "ok"


def test_2fa_secret_is_encrypted_at_rest(client: TestClient, outbox: Outbox, db: Session) -> None:
    create_verified_user(client, outbox)
    login(client)
    secret = client.post("/api/auth/2fa/setup").json()["secret"]

    stored = db.scalars(select(User)).one().totp_secret_encrypted
    assert stored is not None
    assert secret not in stored


def test_protected_routes_require_login(client: TestClient) -> None:
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/2fa/setup").status_code == 401
