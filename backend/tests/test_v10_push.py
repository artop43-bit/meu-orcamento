"""v1.0 (C): notificações no aparelho (Web Push)."""

import json
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.email import OutgoingEmail
from app.models import PushSubscription
from app.services import budget as budget_service
from app.services import notify
from tests.conftest import create_verified_user, login

TZ = ZoneInfo("America/Sao_Paulo")
SUB = {
    "endpoint": "https://push.example.com/abc123",
    "keys": {"p256dh": "BOrW1j4ZcGzN0pV4qX1k8Q2o", "auth": "k8JxLp0aQ9m2"},
}


@pytest.fixture(autouse=True)
def fixed_current_month(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(budget_service, "current_month", lambda *_: date(2030, 1, 1))


@pytest.fixture
def user(client: TestClient, outbox: list[OutgoingEmail]) -> TestClient:
    create_verified_user(client, outbox)
    login(client)
    return client


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Liga o push (chaves de teste) e captura o que seria enviado."""
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(get_settings(), "vapid_public_key", "BPUBLICA_DE_TESTE")
    monkeypatch.setattr(get_settings(), "vapid_private_key", "privada-de-teste")

    def fake_webpush(**kwargs: Any) -> None:
        calls.append({**kwargs, "payload": json.loads(kwargs["data"])})

    import pywebpush

    monkeypatch.setattr(pywebpush, "webpush", fake_webpush)
    return calls


def test_disabled_without_keys(user: TestClient) -> None:
    config = user.get("/api/push").json()
    assert config["enabled"] is False and config["public_key"] == ""
    assert user.post("/api/push/subscribe", json=SUB).status_code == 503


def test_subscribe_test_and_unsubscribe(user: TestClient, sent: list, db: Session) -> None:
    config = user.get("/api/push").json()
    assert config["enabled"] is True and config["public_key"] == "BPUBLICA_DE_TESTE"
    assert user.post("/api/push/subscribe", json=SUB).json()["devices"] == 1
    # Inscrever de novo o mesmo aparelho não duplica.
    assert user.post("/api/push/subscribe", json=SUB).json()["devices"] == 1
    assert user.post("/api/push/test").json() == {"sent": 1}
    assert sent[-1]["payload"]["title"] == "Notificações ativadas"
    assert sent[-1]["subscription_info"]["endpoint"] == SUB["endpoint"]
    bad = {**SUB, "endpoint": "http://inseguro.example.com/x"}
    assert user.post("/api/push/subscribe", json=bad).status_code == 400
    assert (
        user.post("/api/push/unsubscribe", json={"endpoint": SUB["endpoint"]}).json()["devices"]
        == 0
    )


def test_expired_subscription_is_removed(
    user: TestClient, sent: list, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user.post("/api/push/subscribe", json=SUB)
    import pywebpush

    class Gone:
        status_code = 410

    def gone(**_: Any) -> None:
        raise pywebpush.WebPushException("expirou", response=Gone())

    monkeypatch.setattr(pywebpush, "webpush", gone)
    assert user.post("/api/push/test").json() == {"sent": 0}
    assert db.scalar(select(func.count()).select_from(PushSubscription)) == 0


def test_due_reminder_goes_to_device_even_without_email(
    user: TestClient, sent: list, db: Session, outbox: list[OutgoingEmail]
) -> None:
    user.post("/api/push/subscribe", json=SUB)
    user.patch("/api/notifications/prefs", json={"notify_due": False})
    user.post(
        "/api/months/2030-01/expenses",
        json={"description": "Aluguel", "amount": "1500.00", "due_date": "2030-01-13"},
    )
    before = len(outbox)
    notify.run_daily(db, datetime(2030, 1, 10, 9, tzinfo=TZ))
    assert len(outbox) == before  # sem e-mail
    assert [c["payload"]["tag"] for c in sent] == ["due"]
    assert sent[0]["payload"]["url"] == "/calendario"
    # Desligar o tipo "vencimentos" no aparelho para de notificar.
    user.patch("/api/push/prefs", json={"push_due": False})
    sent.clear()
    notify.run_daily(db, datetime(2030, 1, 11, 9, tzinfo=TZ))
    assert sent == []


def test_messages_and_important_announcements(
    client: TestClient,
    sent: list,
    db: Session,
    outbox: list[OutgoingEmail],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_verified_user(client, outbox, "ana@example.com")
    login(client, "ana@example.com")
    client.post("/api/push/subscribe", json=SUB)
    client.patch("/api/push/prefs", json={"push_messages": False})
    client.post("/api/auth/logout")
    monkeypatch.setattr(get_settings(), "admin_emails", "chefe@example.com")
    create_verified_user(client, outbox, "chefe@example.com")
    client.post("/api/auth/logout")
    login(client, "chefe@example.com")
    client.post("/api/admin/announcements", json={"title": "Comum", "body": "Recado comum."})
    assert sent == []
    client.post(
        "/api/admin/announcements",
        json={"title": "Manutenção", "body": "Hoje às 22h.", "important": True},
    )
    assert [c["payload"]["title"] for c in sent] == ["Manutenção"]
