"""v1.9.0: avisos por webhook (Discord, Slack ou qualquer endereço https)."""

import json
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.email import OutgoingEmail
from app.core.errors import AppError
from app.models import InboxItem, User
from app.services import notify, webhook
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


# ---------------------------------------------------------------- avisos do dia (Task 2)

TZ = ZoneInfo("America/Sao_Paulo")


@pytest.fixture
def fixed_month(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import budget as budget_service

    monkeypatch.setattr(budget_service, "current_month", lambda *_: date(2030, 1, 1))


def _quiet(user: TestClient) -> None:
    """E-mail e aparelho desligados: só o webhook pode receber."""
    user.patch(
        "/api/notifications/prefs",
        json={"notify_due": False, "notify_monthly": False, "notify_weekly": False},
    )


def _events(posts: list) -> list[str]:
    return [payload["event"] for _, payload in posts]


def test_vencimento_vai_ao_webhook_sem_aparelho(
    user: TestClient, db: Session, posts: list, fixed_month: None
) -> None:
    _quiet(user)
    _connect(db, kinds=["due"])
    user.post(
        "/api/months/2030-01/expenses",
        json={"description": "Aluguel", "amount": "1500.00", "due_date": "2030-01-13"},
    )
    notify.run_daily(db, datetime(2030, 1, 10, 9, tzinfo=TZ))
    assert _events(posts) == ["due"]
    rows = [row["description"] for s in posts[0][1]["sections"] for row in s["rows"]]
    assert "Aluguel" in rows
    notify.run_daily(db, datetime(2030, 1, 10, 10, tzinfo=TZ))
    assert len(posts) == 1  # não repete no mesmo dia


def test_resumo_do_mes_e_disponivel_hoje(
    user: TestClient, db: Session, posts: list, fixed_month: None
) -> None:
    _quiet(user)
    _connect(db, kinds=["monthly", "daily"])
    user.post("/api/months/2030-01/incomes", json={"description": "Salário", "amount": "3000.00"})
    user.post("/api/months/2030-02/incomes", json={"description": "Salário", "amount": "3000.00"})
    user.post(
        "/api/months/2030-01/expenses",
        json={"description": "Mercado", "amount": "200.00", "due_date": "2030-01-05", "paid": True},
    )
    notify.run_daily(db, datetime(2030, 2, 1, 9, tzinfo=TZ))
    assert sorted(_events(posts)) == ["daily", "monthly"]


def test_resumo_semana_segunda(
    user: TestClient, db: Session, posts: list, fixed_month: None
) -> None:
    _quiet(user)
    _connect(db, kinds=["weekly"])
    user.post(
        "/api/months/2030-01/expenses",
        json={"description": "Internet", "amount": "99.90", "due_date": "2030-01-16"},
    )
    notify.run_daily(db, datetime(2030, 1, 14, 8, 30, tzinfo=TZ))
    assert _events(posts) == ["weekly"]


def test_tipo_desligado_nao_envia(
    user: TestClient, db: Session, posts: list, fixed_month: None
) -> None:
    _quiet(user)
    _connect(db, kinds=["weekly"])
    user.post(
        "/api/months/2030-01/expenses",
        json={"description": "Aluguel", "amount": "1500.00", "due_date": "2030-01-13"},
    )
    notify.run_daily(db, datetime(2030, 1, 10, 9, tzinfo=TZ))
    assert posts == []


def test_esconder_valores(user: TestClient, db: Session, posts: list, fixed_month: None) -> None:
    _quiet(user)
    user.patch("/api/notifications/prefs", json={"notify_hide_values": True})
    _connect(db, kinds=["due", "weekly"])
    user.post(
        "/api/months/2030-01/expenses",
        json={"description": "Aluguel", "amount": "1500.00", "due_date": "2030-01-15"},
    )
    notify.run_daily(db, datetime(2030, 1, 14, 9, tzinfo=TZ))
    assert posts and all("R$" not in json.dumps(p, ensure_ascii=False) for _, p in posts)


def test_webhook_fora_do_ar_nao_quebra(
    client: TestClient,
    db: Session,
    outbox: list[OutgoingEmail],
    monkeypatch: pytest.MonkeyPatch,
    fixed_month: None,
) -> None:
    def broken(url: str, payload: dict[str, Any]) -> bool:
        raise RuntimeError("caiu")

    monkeypatch.setattr(webhook, "_post", broken)
    for address in ("ana@example.com", "bia@example.com"):
        create_verified_user(client, outbox, address)
        login(client, address)
        client.post(
            "/api/months/2030-01/expenses",
            json={"description": "Aluguel", "amount": "1500.00", "due_date": "2030-01-13"},
        )
        client.post("/api/auth/logout")
    _connect(db, kinds=["due"])
    outbox.clear()
    assert notify.run_daily(db, datetime(2030, 1, 10, 9, tzinfo=TZ))["due"] == 2
    assert {m.to for m in outbox} == {"ana@example.com", "bia@example.com"}


def test_mensagens_da_caixa(
    client: TestClient,
    db: Session,
    outbox: list[OutgoingEmail],
    posts: list,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import get_settings

    create_verified_user(client, outbox, "ana@example.com")
    client.post("/api/auth/logout")
    _connect(db, kinds=["messages"])
    monkeypatch.setattr(get_settings(), "admin_emails", "chefe@example.com")
    create_verified_user(client, outbox, "chefe@example.com")
    login(client, "chefe@example.com")
    client.post("/api/admin/announcements", json={"title": "Novidade", "body": "Recado."})
    assert [p["title"] for _, p in posts] == ["Novidade"]


def test_alertas_passam_pelo_push_send(user: TestClient, db: Session, posts: list) -> None:
    from app.services import push

    ana = _connect(db, kinds=["alerts"])
    push.send(db, ana, "alerts", "Gasto fora do padrão", "Mercado subiu.", "/analises")
    push.send(db, ana, "messages", "Outro", "x")
    assert _events(posts) == ["alerts"]


def test_teste_do_aparelho_nao_vai_ao_webhook(
    user: TestClient, db: Session, posts: list, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "vapid_public_key", "BPUBLICA_DE_TESTE")
    monkeypatch.setattr(get_settings(), "vapid_private_key", "privada-de-teste")
    _connect(db)
    user.post("/api/push/test")
    assert posts == []


# ---------------------------------------------------------------- API (Task 3)


def test_api_fluxo_completo(user: TestClient, posts: list) -> None:
    empty = user.get("/api/notifications/webhook").json()
    assert empty == {
        "configured": False,
        "hint": None,
        "service": None,
        "kinds": [],
        "paused": False,
    }
    saved = user.put("/api/notifications/webhook", json={"url": DISCORD}).json()
    assert saved["configured"] is True and saved["hint"] == "discord.com/…a8F2"
    assert saved["service"] == "discord" and saved["kinds"] == []
    kinds = user.patch("/api/notifications/webhook", json={"kinds": ["weekly", "due"]}).json()
    assert kinds["kinds"] == ["due", "weekly"]
    assert user.post("/api/notifications/webhook/test").json() == {"ok": True}
    [(url, payload)] = posts
    assert url == DISCORD and payload["embeds"][0]["title"] == "Webhook conectado"
    gone = user.delete("/api/notifications/webhook").json()
    assert gone["configured"] is False and gone["kinds"] == []


def test_api_nunca_devolve_url_inteira(user: TestClient) -> None:
    responses = [
        user.put("/api/notifications/webhook", json={"url": DISCORD}),
        user.get("/api/notifications/webhook"),
        user.patch("/api/notifications/webhook", json={"kinds": ["due"]}),
    ]
    assert all("xyza8F2" not in r.text for r in responses)


def test_api_url_invalida_400(user: TestClient) -> None:
    response = user.put("/api/notifications/webhook", json={"url": "http://exemplo.com/a"})
    assert response.status_code == 400 and response.json()["error"] == "webhook_invalido"


def test_api_kind_desconhecido_422(user: TestClient) -> None:
    user.put("/api/notifications/webhook", json={"url": GENERIC})
    response = user.patch("/api/notifications/webhook", json={"kinds": ["spam"]})
    assert response.status_code == 422


def test_api_teste_sem_endereco_400(user: TestClient) -> None:
    assert user.post("/api/notifications/webhook/test").status_code == 400


def test_api_teste_tira_pausa(user: TestClient, db: Session, posts: list) -> None:
    ana = _connect(db)
    ana.webhook_failures = webhook.MAX_FAILURES
    db.commit()
    assert user.get("/api/notifications/webhook").json()["paused"] is True
    assert user.post("/api/notifications/webhook/test").json() == {"ok": True}
    assert user.get("/api/notifications/webhook").json()["paused"] is False


def test_api_salvar_de_novo_tira_pausa(user: TestClient, db: Session) -> None:
    ana = _connect(db)
    ana.webhook_failures = webhook.MAX_FAILURES
    db.commit()
    assert user.put("/api/notifications/webhook", json={"url": SLACK}).json()["paused"] is False


def test_api_exige_login(client: TestClient) -> None:
    assert client.get("/api/notifications/webhook").status_code == 401
