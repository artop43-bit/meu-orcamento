"""v1.9.0: avisos por webhook (Discord, Slack ou qualquer endereço https)."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.email import OutgoingEmail
from app.core.errors import AppError
from app.models import InboxItem, User
from app.services import webhook
from app.services.notify import Section
from tests.conftest import create_verified_user, login

PUBLIC = ["93.184.216.34"]
DISCORD = "https://discord.com/api/webhooks/123/xyza8F2"
SLACK = "https://hooks.slack.com/services/T000/B000/XXXX"
GENERIC = "https://n8n.meu.dev/webhook/abc"


@pytest.fixture(autouse=True)
def public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(webhook, "_resolve", lambda host: PUBLIC)


@pytest.fixture
def posts(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, Any]]]:
    """Captura o que seria enviado ao webhook (sem rede)."""
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_post(url: str, payload: dict[str, Any]) -> bool:
        calls.append((url, payload))
        return True

    monkeypatch.setattr(webhook, "_post", fake_post)
    return calls


@pytest.fixture
def user(client: TestClient, outbox: list[OutgoingEmail]) -> TestClient:
    create_verified_user(client, outbox)
    login(client)
    return client


def _ana(db: Session) -> User:
    return db.scalars(select(User).where(User.email == "ana@example.com")).one()


def _connect(db: Session, url: str = GENERIC, kinds: list[str] | None = None) -> User:
    ana = _ana(db)
    ana.webhook_url = url
    ana.webhook_kinds = webhook.dump_kinds(kinds or list(webhook.KINDS))
    ana.webhook_failures = 0
    db.commit()
    return ana


# ---------------------------------------------------------------- endereço


@pytest.mark.parametrize(
    "url",
    [
        "http://exemplo.com/a",
        "https://usuario:senha@exemplo.com/a",
        "ftp://exemplo.com/a",
        "https://",
        "https://exemplo.com/" + "a" * 490,
        "nada",
    ],
)
def test_validate_rejeita_http_e_credenciais(url: str) -> None:
    with pytest.raises(AppError) as error:
        webhook.validate_url(url)
    assert error.value.code == "webhook_invalido"


@pytest.mark.parametrize(
    "ip", ["127.0.0.1", "10.0.0.5", "192.168.1.1", "169.254.169.254", "::1", "fd00::1", "0.0.0.0"]
)
def test_validate_rejeita_ip_interno(monkeypatch: pytest.MonkeyPatch, ip: str) -> None:
    monkeypatch.setattr(webhook, "_resolve", lambda host: [*PUBLIC, ip])
    with pytest.raises(AppError) as error:
        webhook.validate_url(GENERIC)
    assert error.value.code == "webhook_invalido"


def test_validate_aceita_publico() -> None:
    assert webhook.validate_url(f"  {DISCORD}  ") == DISCORD


def test_validate_rejeita_host_inexistente(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(host: str) -> list[str]:
        raise OSError("sem DNS")

    monkeypatch.setattr(webhook, "_resolve", fail)
    with pytest.raises(AppError):
        webhook.validate_url(GENERIC)


def test_service_of() -> None:
    assert webhook.service_of(DISCORD) == "discord"
    assert webhook.service_of("https://discordapp.com/api/webhooks/1/abc") == "discord"
    assert webhook.service_of(SLACK) == "slack"
    assert webhook.service_of(GENERIC) == "generic"
    assert webhook.service_of("https://discord.com.golpe.io/api/webhooks/1") == "generic"


def test_url_hint() -> None:
    assert webhook.url_hint(DISCORD) == "discord.com/…a8F2"


# ---------------------------------------------------------------- formato

SECTIONS = [Section("Vencem em breve", [("Internet", "20/01", "R$ 150,00")], note="Pague em dia.")]


def test_payload_discord() -> None:
    payload = webhook.build_payload(
        "discord", "due", "Contas a vencer", "1 conta", "/calendario", SECTIONS
    )
    [embed] = payload["embeds"]
    assert embed["title"] == "Contas a vencer"
    assert "1 conta" in embed["description"]
    assert embed["url"].endswith("/calendario")
    assert embed["fields"][0]["name"] == "Vencem em breve"
    assert "Internet" in embed["fields"][0]["value"] and "R$ 150,00" in embed["fields"][0]["value"]
    assert "text" not in payload


def test_payload_slack() -> None:
    payload = webhook.build_payload(
        "slack", "due", "Contas a vencer", "1 conta", "/calendario", SECTIONS
    )
    assert payload["text"].startswith("*Contas a vencer*")
    assert "1 conta" in payload["text"] and "Internet" in payload["text"]


def test_payload_generico() -> None:
    payload = webhook.build_payload(
        "generic", "due", "Contas a vencer", "1 conta", "/calendario", SECTIONS
    )
    assert payload["event"] == "due"
    assert payload["title"] == "Contas a vencer" and payload["body"] == "1 conta"
    assert payload["link"].startswith("http") and payload["link"].endswith("/calendario")
    assert "T" in payload["sent_at"]
    assert payload["sections"] == [
        {
            "title": "Vencem em breve",
            "rows": [{"description": "Internet", "date": "20/01", "value": "R$ 150,00"}],
            "note": "Pague em dia.",
        }
    ]
    assert payload["text"] == payload["content"] and "Internet" in payload["text"]


# ---------------------------------------------------------------- envio


def test_send_respeita_tipos(user: TestClient, db: Session, posts: list) -> None:
    ana = _connect(db, kinds=["weekly"])
    assert webhook.send(db, ana, "due", "t", "b") is False
    assert webhook.send(db, ana, "weekly", "t", "b") is True
    assert len(posts) == 1 and posts[0][1]["event"] == "weekly"
    assert webhook.send(db, ana, "due", "t", "b", force=True) is True


def test_send_sem_endereco(user: TestClient, db: Session, posts: list) -> None:
    assert webhook.send(db, _ana(db), "due", "t", "b") is False
    assert posts == []


def test_send_conta_falhas_e_pausa(
    user: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(webhook, "_post", lambda url, payload: calls.append(url) or False)
    ana = _connect(db)
    for _ in range(webhook.MAX_FAILURES):
        assert webhook.send(db, ana, "due", "t", "b") is False
    assert webhook.paused(ana) and not webhook.wants(ana, "due")
    notes = db.scalars(select(InboxItem).where(InboxItem.title == "Webhook pausado")).all()
    assert len(notes) == 1
    webhook.send(db, ana, "due", "t", "b")
    assert len(calls) == webhook.MAX_FAILURES


def test_send_sucesso_zera_falhas(user: TestClient, db: Session, posts: list) -> None:
    ana = _connect(db)
    ana.webhook_failures = 3
    db.commit()
    assert webhook.send(db, ana, "due", "t", "b") is True
    assert ana.webhook_failures == 0


def test_send_revalida_ip(
    user: TestClient, db: Session, posts: list, monkeypatch: pytest.MonkeyPatch
) -> None:
    ana = _connect(db)
    monkeypatch.setattr(webhook, "_resolve", lambda host: ["127.0.0.1"])
    assert webhook.send(db, ana, "due", "t", "b") is False
    assert posts == []
