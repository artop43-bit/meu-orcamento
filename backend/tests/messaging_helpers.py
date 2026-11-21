"""Ajudantes dos testes da Mensageria (conector falso, eventos e consultas ao banco)."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import MessagingChat, MessagingMessage, MessagingSession, User
from app.services.messaging import connector_client
from tests.conftest import create_verified_user, login

TOKEN = "chave-do-conector-de-teste"
CONNECTOR_URL = "http://conector.test"


class FakeConnector:
    """Guarda as chamadas que a API faria ao conector (nada sai para a rede)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.fail = False

    def __call__(self, path: str, payload: dict[str, Any] | None = None) -> None:
        self.calls.append((path, payload or {}))
        if self.fail:
            raise connector_client.ConnectorError("fora do ar")

    def paths(self) -> list[str]:
        return [path for path, _ in self.calls]


def install_fake_connector(monkeypatch: pytest.MonkeyPatch) -> FakeConnector:
    """Liga o recurso (URL e chave configuradas) com um conector falso no lugar da rede."""
    settings = get_settings()
    monkeypatch.setattr(settings, "messaging_connector_url", CONNECTOR_URL)
    monkeypatch.setattr(settings, "messaging_connector_token", TOKEN)
    fake = FakeConnector()
    monkeypatch.setattr(connector_client, "_post", fake)
    return fake


def auth(client: TestClient, outbox: list, email: str = "ana@example.com") -> None:
    create_verified_user(client, outbox, email)
    assert login(client, email).status_code == 200


def session_row(db: Session, email: str = "ana@example.com") -> MessagingSession:
    db.expire_all()
    row = db.scalar(
        select(MessagingSession)
        .join(User, User.id == MessagingSession.user_id)
        .where(User.email == email)
    )
    assert row is not None
    return row


def chat_rows(db: Session) -> list[MessagingChat]:
    db.expire_all()
    return list(db.scalars(select(MessagingChat).order_by(MessagingChat.created_at)).all())


def message_row(db: Session, **where: Any) -> MessagingMessage:
    db.expire_all()
    stmt = select(MessagingMessage)
    for field, value in where.items():
        stmt = stmt.where(getattr(MessagingMessage, field) == value)
    row = db.scalar(stmt)
    assert row is not None
    return row


def connector_headers(token: str = TOKEN) -> dict[str, str]:
    # Sem o X-Requested-With da tela: o conector não usa cookie, só a chave.
    return {"X-Connector-Token": token, "X-Requested-With": ""}


def send_events(client: TestClient, *events: dict[str, Any]) -> dict[str, int]:
    res = client.post(
        "/api/messaging/connector/events",
        json={"events": list(events)},
        headers=connector_headers(),
    )
    assert res.status_code == 200, res.text
    return res.json()


def claim(client: TestClient, *session_ids: str, limit: int | None = None) -> list[dict]:
    params: dict[str, Any] = {"session_ids": ",".join(session_ids)}
    if limit is not None:
        params["limit"] = limit
    res = client.get("/api/messaging/connector/outbox", params=params, headers=connector_headers())
    assert res.status_code == 200, res.text
    return res.json()["items"]


def connect_ready(
    client: TestClient,
    db: Session,
    email: str = "ana@example.com",
    phone: str = "5511988887777",
) -> str:
    """Conecta pela tela e simula o conector avisando que o número está pronto."""
    assert client.post("/api/messaging/session/connect").status_code == 200
    session_id = str(session_row(db, email).id)
    result = send_events(
        client,
        {
            "type": "status",
            "session_id": session_id,
            "status": "ready",
            "phone": phone,
            "display_name": "WhatsApp da Ana",
            "wa_jid": f"{phone}:7@s.whatsapp.net",
        },
    )
    assert result == {"processed": 1, "ignored": 0}
    return session_id


def inbound(
    session_id: str,
    external_id: str,
    remote_jid: str,
    body: str = "Oi!",
    **extra: Any,
) -> dict[str, Any]:
    return {
        "type": "message",
        "session_id": session_id,
        "external_id": external_id,
        "remote_jid": remote_jid,
        "from_me": False,
        "body": body,
        "message_type": "chat",
        "timestamp": "2030-01-10T12:00:00Z",
        **extra,
    }
