"""Testes da Mensageria pela tela: sessão, conversas, mensagens e ponte com o Orçamento."""

import json
import urllib.error
import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.types import utcnow
from app.services import admin as admin_service
from app.services.messaging import connector_client
from app.services.messaging import media as media_service
from tests.messaging_helpers import (
    CONNECTOR_URL,
    TOKEN,
    FakeConnector,
    auth,
    connect_ready,
    inbound,
    install_fake_connector,
    message_row,
    send_events,
    session_row,
)


@pytest.fixture
def connector(monkeypatch: pytest.MonkeyPatch) -> FakeConnector:
    return install_fake_connector(monkeypatch)


def test_messaging_requires_auth(client: TestClient) -> None:
    assert client.get("/api/messaging/session").status_code == 401
    assert client.post("/api/messaging/session/connect").status_code == 401
    assert client.post("/api/messaging/session/disconnect").status_code == 401
    assert client.get("/api/messaging/chats").status_code == 401
    assert client.get(f"/api/messaging/chats/{uuid.uuid4()}").status_code == 401
    assert client.get("/api/messaging/budget-context").status_code == 401


def test_old_bridge_routes_are_gone(client: TestClient, outbox: list) -> None:
    auth(client, outbox)
    assert client.post("/api/messaging/session/bridge-token").status_code in {404, 405}
    assert client.get("/api/messaging/bridge/status").status_code == 404


def test_session_summary_without_connector(
    client: TestClient, outbox: list, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "messaging_connector_token", "")
    auth(client, outbox)
    s0 = client.get("/api/messaging/session").json()
    assert s0["status"] == "disconnected"
    assert s0["connected"] is False
    assert s0["available"] is False
    assert s0["phone"] is None
    assert s0["phone_display"] == ""
    assert s0["qr_code"] is None
    assert s0["pending_outbox"] == 0
    assert "has_bridge_token" not in s0

    res = client.post("/api/messaging/session/connect")
    assert res.status_code == 503
    assert res.json()["error"] == "connector_unavailable"
    assert res.json()["message"] == "A conexão com o WhatsApp não está disponível neste servidor."


def test_connect_starts_connector_and_qr_flow(
    client: TestClient, outbox: list, db: Session, connector: FakeConnector
) -> None:
    auth(client, outbox)
    assert client.get("/api/messaging/session").json()["available"] is True

    res = client.post("/api/messaging/session/connect")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "connecting"
    row = session_row(db)
    assert row.wanted is True
    assert connector.paths() == [f"/sessions/{row.id}/start"]

    # O conector manda o QR (string crua) e a tela mostra.
    send_events(
        client, {"type": "status", "session_id": str(row.id), "status": "qr", "qr": "2@abc,def"}
    )
    summary = client.get("/api/messaging/session").json()
    assert summary["status"] == "qr"
    assert summary["qr_code"] == "2@abc,def"

    # Pedir de novo reinicia o pedido (QR novo) e limpa o QR antigo.
    again = client.post("/api/messaging/session/connect").json()
    assert again["status"] == "connecting"
    assert again["qr_code"] is None
    assert connector.paths()[-1] == f"/sessions/{row.id}/start"


def test_connect_marks_error_when_connector_is_down(
    client: TestClient, outbox: list, db: Session, connector: FakeConnector
) -> None:
    auth(client, outbox)
    connector.fail = True
    res = client.post("/api/messaging/session/connect")
    assert res.status_code == 200
    assert res.json()["status"] == "error"
    assert res.json()["last_error"] == "Não foi possível falar com o conector do WhatsApp."
    # Continua pedido: quando o conector voltar, ele restaura a sessão.
    assert session_row(db).wanted is True


def test_connect_refuses_when_server_is_full(
    client: TestClient,
    outbox: list,
    db: Session,
    connector: FakeConnector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "messaging_max_sessions", 1)
    auth(client, outbox, "ana@example.com")
    assert client.post("/api/messaging/session/connect").status_code == 200
    # A própria sessão não conta: pedir de novo continua valendo.
    assert client.post("/api/messaging/session/connect").status_code == 200

    client.post("/api/auth/logout")
    auth(client, outbox, "bruno@example.com")
    res = client.post("/api/messaging/session/connect")
    assert res.status_code == 409
    assert res.json()["error"] == "sessions_full"
    assert session_row(db, "bruno@example.com").wanted is False
    assert len(connector.calls) == 2


def test_disconnect_logs_out_and_clears_data(
    client: TestClient, outbox: list, db: Session, connector: FakeConnector
) -> None:
    auth(client, outbox)
    session_id = connect_ready(client, db)
    ready = client.get("/api/messaging/session").json()
    assert ready["connected"] is True
    assert ready["phone"] == "5511988887777"
    assert ready["phone_display"] == "+55 (11) 98888-7777"
    assert ready["display_name"] == "WhatsApp da Ana"

    res = client.post("/api/messaging/session/disconnect")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "disconnected"
    assert body["connected"] is False
    assert body["phone"] is None
    assert body["display_name"] is None
    row = session_row(db)
    assert row.wanted is False
    assert row.wa_jid is None
    assert connector.calls[-1] == (f"/sessions/{session_id}/stop", {"logout": True})

    # Melhor esforço: com o conector fora do ar, desconectar funciona do mesmo jeito.
    connector.fail = True
    assert client.post("/api/messaging/session/disconnect").status_code == 200


def test_chat_lifecycle_and_phone_normalization(client: TestClient, outbox: list) -> None:
    auth(client, outbox)

    # Número brasileiro sem DDI recebe 55 e vira @s.whatsapp.net.
    res = client.post(
        "/api/messaging/chats",
        json={"phone": "(11) 99876-5432", "name": "Carlos Silva"},
    )
    assert res.status_code == 201, res.text
    chat = res.json()
    assert chat["phone"] == "5511998765432"
    assert chat["remote_jid"] == "5511998765432@s.whatsapp.net"
    assert chat["lid_jid"] is None
    assert chat["name"] == "Carlos Silva"
    assert chat["phone_display"] == "+55 (11) 99876-5432"

    # Reabrir o mesmo número (em outro formato, até o antigo @c.us) é idempotente.
    same = client.post(
        "/api/messaging/chats",
        json={"phone": "5511998765432@c.us", "notes": "Cliente recorrente"},
    )
    assert same.status_code == 201
    assert same.json()["id"] == chat["id"]
    assert same.json()["notes"] == "Cliente recorrente"

    # Contato só com LID: sem número.
    lid = client.post(
        "/api/messaging/chats",
        json={"phone": "12345678901234@lid", "name": "Contato LID"},
    )
    assert lid.status_code == 201
    assert lid.json()["remote_jid"] == "12345678901234@lid"
    assert lid.json()["lid_jid"] == "12345678901234@lid"
    assert lid.json()["phone"] is None
    assert lid.json()["phone_display"] == ""

    bad = client.post("/api/messaging/chats", json={"phone": "123"})
    assert bad.status_code == 400
    assert bad.json()["error"] == "invalid_phone"

    # Abrir uma conversa pelo id.
    one = client.get(f"/api/messaging/chats/{chat['id']}")
    assert one.status_code == 200
    assert one.json()["notes"] == "Cliente recorrente"

    patched = client.patch(
        f"/api/messaging/chats/{chat['id']}",
        json={"pinned": True, "name": "Carlos S."},
    )
    assert patched.status_code == 200
    assert patched.json()["pinned"] is True
    assert patched.json()["name"] == "Carlos S."

    listed = client.get("/api/messaging/chats", params={"q": "99876"}).json()
    assert [c["id"] for c in listed] == [chat["id"]]

    assert (
        client.patch(f"/api/messaging/chats/{chat['id']}", json={"archived": True}).status_code
        == 200
    )
    assert all(c["id"] != chat["id"] for c in client.get("/api/messaging/chats").json())
    archived = client.get("/api/messaging/chats", params={"filter": "archived"}).json()
    assert [c["id"] for c in archived] == [chat["id"]]

    assert client.delete(f"/api/messaging/chats/{chat['id']}").status_code == 204
    missing = client.get(f"/api/messaging/chats/{chat['id']}")
    assert missing.status_code == 404
    assert missing.json()["error"] == "chat_not_found"
    assert client.get(f"/api/messaging/chats/{chat['id']}/messages").status_code == 404


def test_send_is_blocked_while_disconnected(client: TestClient, outbox: list) -> None:
    auth(client, outbox)
    chat = client.post("/api/messaging/chats", json={"phone": "5511991112222"}).json()
    res = client.post(f"/api/messaging/chats/{chat['id']}/messages", json={"body": "Oi"})
    assert res.status_code == 409
    assert res.json()["error"] == "whatsapp_disconnected"
    assert res.json()["message"] == "Conecte o WhatsApp para enviar mensagens."
    # Nada fica gravado como "enviada" sem conexão.
    page = client.get(f"/api/messaging/chats/{chat['id']}/messages").json()
    assert page["items"] == []


def test_send_queues_pending_and_flushes(
    client: TestClient, outbox: list, db: Session, connector: FakeConnector
) -> None:
    auth(client, outbox)
    session_id = connect_ready(client, db)
    chat = client.post(
        "/api/messaging/chats", json={"phone": "5511991112222", "name": "Marina"}
    ).json()

    m1 = client.post(
        f"/api/messaging/chats/{chat['id']}/messages", json={"body": "Oi Marina, tudo bem?"}
    )
    assert m1.status_code == 201, m1.text
    first = m1.json()
    assert first["direction"] == "out"
    assert first["status"] == "pending"
    assert first["sent_at"] is None
    assert first["updated_at"]
    assert connector.calls[-1] == (f"/sessions/{session_id}/flush", {})

    m2 = client.post(
        f"/api/messaging/chats/{chat['id']}/messages",
        json={"body": "Confirmando o horário de hoje.", "reply_to_id": first["id"]},
    )
    assert m2.status_code == 201
    assert m2.json()["reply_to_id"] == first["id"]
    assert m2.json()["reply_preview"] == "Oi Marina, tudo bem?"

    bad_reply = client.post(
        f"/api/messaging/chats/{chat['id']}/messages",
        json={"body": "x", "reply_to_id": str(uuid.uuid4())},
    )
    assert bad_reply.status_code == 404

    # Conector fora do ar: a mensagem fica na fila e a tela não recebe erro.
    connector.fail = True
    m3 = client.post(f"/api/messaging/chats/{chat['id']}/messages", json={"body": "Mais uma"})
    assert m3.status_code == 201
    assert m3.json()["status"] == "pending"

    page = client.get(f"/api/messaging/chats/{chat['id']}/messages").json()
    assert [m["id"] for m in page["items"]] == [first["id"], m2.json()["id"], m3.json()["id"]]
    assert client.get("/api/messaging/session").json()["pending_outbox"] == 3


def test_messages_since_and_cursor(
    client: TestClient, outbox: list, db: Session, connector: FakeConnector
) -> None:
    auth(client, outbox)
    session_id = connect_ready(client, db)
    jid = "5511977776666@s.whatsapp.net"
    send_events(
        client,
        inbound(session_id, "IN-1", jid, "Primeira", timestamp="2030-01-10T12:00:00Z"),
        inbound(session_id, "IN-2", jid, "Segunda", timestamp="2030-01-10T12:01:00Z"),
        inbound(session_id, "IN-3", jid, "Terceira", timestamp="2030-01-10T12:02:00Z"),
    )
    chat_id = str(message_row(db, external_id="IN-1").chat_id)
    url = f"/api/messaging/chats/{chat_id}/messages"

    full = client.get(url).json()
    assert [m["body"] for m in full["items"]] == ["Primeira", "Segunda", "Terceira"]
    assert full["cursor"] == max(m["updated_at"] for m in full["items"])

    # Só as duas mais recentes, ainda em ordem crescente.
    latest = client.get(url, params={"limit": 2}).json()
    assert [m["body"] for m in latest["items"]] == ["Segunda", "Terceira"]

    # Deixa as duas primeiras "antigas": o since só traz o que mudou (com 5 s de sobra).
    old = utcnow() - timedelta(hours=1)
    for ext in ("IN-1", "IN-2"):
        row = message_row(db, external_id=ext)
        row.updated_at = old
        db.commit()
    since = full["cursor"]
    changed = client.get(url, params={"since": since}).json()
    assert [m["body"] for m in changed["items"]] == ["Terceira"]
    assert changed["cursor"] >= since

    # Sem novidade: lista vazia e o cursor continua o mesmo.
    future = (utcnow() + timedelta(hours=1)).isoformat()
    empty = client.get(url, params={"since": future}).json()
    assert empty["items"] == []
    assert empty["cursor"].startswith(future[:19])

    # Uma mudança numa mensagem antiga (ex.: resposta a ela) volta a aparecer no since.
    send_events(
        client,
        inbound(session_id, "IN-4", jid, "Respondendo", quoted_external_id="IN-1"),
    )
    row = message_row(db, external_id="IN-1")
    row.body = "Primeira (editada)"
    db.commit()
    again = client.get(url, params={"since": since}).json()
    bodies = [m["body"] for m in again["items"]]
    assert "Primeira (editada)" in bodies and "Respondendo" in bodies
    assert "Segunda" not in bodies
    reply = next(m for m in again["items"] if m["body"] == "Respondendo")
    assert reply["reply_preview"] == "Primeira (editada)"


def test_messages_since_has_five_seconds_of_overlap(
    client: TestClient, outbox: list, db: Session, connector: FakeConnector
) -> None:
    auth(client, outbox)
    session_id = connect_ready(client, db)
    jid = "5511977776666@s.whatsapp.net"
    send_events(
        client,
        inbound(session_id, "OV-1", jid, "Mudou 3 s antes", timestamp="2030-01-10T12:00:00Z"),
        inbound(session_id, "OV-2", jid, "Mudou 10 s antes", timestamp="2030-01-10T12:01:00Z"),
        inbound(session_id, "OV-3", jid, "Mudou depois", timestamp="2030-01-10T12:02:00Z"),
    )
    since = utcnow() - timedelta(minutes=1)
    for ext, offset in (("OV-1", -3), ("OV-2", -10), ("OV-3", 1)):
        row = message_row(db, external_id=ext)
        row.updated_at = since + timedelta(seconds=offset)
        db.commit()
    chat_id = str(message_row(db, external_id="OV-1").chat_id)

    page = client.get(
        f"/api/messaging/chats/{chat_id}/messages", params={"since": since.isoformat()}
    ).json()
    # Volta o que mudou até 5 s antes do since (sobreposição), em ordem crescente.
    assert [m["external_id"] for m in page["items"]] == ["OV-1", "OV-3"]
    assert page["cursor"] == max(m["updated_at"] for m in page["items"])


def test_read_confirms_at_most_twenty_latest(
    client: TestClient, outbox: list, db: Session, connector: FakeConnector
) -> None:
    auth(client, outbox)
    session_id = connect_ready(client, db)
    jid = "5511977776666@s.whatsapp.net"
    send_events(
        client,
        *[
            inbound(
                session_id,
                f"MUITAS-{n:02d}",
                jid,
                f"Mensagem {n}",
                timestamp=f"2030-01-10T12:{n:02d}:00Z",
            )
            for n in range(25)
        ],
    )
    chat_id = str(message_row(db, external_id="MUITAS-00").chat_id)
    assert client.get(f"/api/messaging/chats/{chat_id}").json()["unread_count"] == 25

    read = client.post(f"/api/messaging/chats/{chat_id}/read")
    assert read.status_code == 200
    assert read.json()["unread_count"] == 0
    # Só as 20 mais recentes vão para o WhatsApp, da mais antiga para a mais nova.
    assert connector.calls[-1] == (
        f"/sessions/{session_id}/read",
        {"remote_jid": jid, "external_ids": [f"MUITAS-{n:02d}" for n in range(5, 25)]},
    )


def test_available_needs_url_and_token(
    client: TestClient, outbox: list, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth(client, outbox)
    settings = get_settings()
    # Só a chave, sem o endereço do conector: recurso indisponível.
    monkeypatch.setattr(settings, "messaging_connector_url", "")
    monkeypatch.setattr(settings, "messaging_connector_token", TOKEN)
    assert client.get("/api/messaging/session").json()["available"] is False
    assert client.post("/api/messaging/session/connect").status_code == 503

    # Só o endereço, sem a chave: também indisponível.
    monkeypatch.setattr(settings, "messaging_connector_url", CONNECTOR_URL)
    monkeypatch.setattr(settings, "messaging_connector_token", "  ")
    assert client.get("/api/messaging/session").json()["available"] is False
    res = client.post("/api/messaging/session/connect")
    assert res.status_code == 503
    assert res.json()["error"] == "connector_unavailable"


def test_read_confirms_on_whatsapp(
    client: TestClient, outbox: list, db: Session, connector: FakeConnector
) -> None:
    auth(client, outbox)
    session_id = connect_ready(client, db)
    jid = "5511977776666@s.whatsapp.net"
    send_events(
        client,
        inbound(session_id, "OLD-1", jid, "Antiga", timestamp="2030-01-10T11:00:00Z"),
    )
    chat_id = str(message_row(db, external_id="OLD-1").chat_id)
    assert client.post(f"/api/messaging/chats/{chat_id}/read").json()["unread_count"] == 0
    assert connector.calls[-1] == (
        f"/sessions/{session_id}/read",
        {"remote_jid": jid, "external_ids": ["OLD-1"]},
    )

    send_events(
        client,
        inbound(session_id, "NEW-1", jid, "Nova 1", timestamp="2030-01-10T12:00:00Z"),
        inbound(session_id, "NEW-2", jid, "Nova 2", timestamp="2030-01-10T12:01:00Z"),
    )
    calls_before = len(connector.calls)
    read = client.post(f"/api/messaging/chats/{chat_id}/read")
    assert read.status_code == 200
    assert read.json()["unread_count"] == 0
    # Só as não lidas (as duas novas), em ordem.
    assert connector.calls[calls_before:] == [
        (
            f"/sessions/{session_id}/read",
            {"remote_jid": jid, "external_ids": ["NEW-1", "NEW-2"]},
        )
    ]

    # Nada para confirmar: não chama o conector.
    client.post(f"/api/messaging/chats/{chat_id}/read")
    assert len(connector.calls) == calls_before + 1

    # Desconectado: zera na tela, mas não chama o conector.
    send_events(client, inbound(session_id, "NEW-3", jid, "Nova 3"))
    session = session_row(db)
    session.status = "disconnected"
    db.commit()
    assert client.post(f"/api/messaging/chats/{chat_id}/read").json()["unread_count"] == 0
    assert len(connector.calls) == calls_before + 1


def test_user_isolation(
    client: TestClient, outbox: list, db: Session, connector: FakeConnector
) -> None:
    auth(client, outbox, "ana@example.com")
    connect_ready(client, db)
    chat = client.post(
        "/api/messaging/chats", json={"phone": "5511991112222", "name": "Marina"}
    ).json()
    assert (
        client.post(f"/api/messaging/chats/{chat['id']}/messages", json={"body": "Oi"}).status_code
        == 201
    )

    client.post("/api/auth/logout")
    auth(client, outbox, "bruno@example.com")
    connect_ready(client, db, "bruno@example.com", phone="5511955554444")
    assert client.get("/api/messaging/chats").json() == []
    assert client.get(f"/api/messaging/chats/{chat['id']}").status_code == 404
    assert client.get(f"/api/messaging/chats/{chat['id']}/messages").status_code == 404
    assert (
        client.post(
            f"/api/messaging/chats/{chat['id']}/messages", json={"body": "invasão"}
        ).status_code
        == 404
    )
    assert client.post(f"/api/messaging/chats/{chat['id']}/read").status_code == 404
    assert client.delete(f"/api/messaging/chats/{chat['id']}").status_code == 404
    assert client.get("/api/messaging/session").json()["pending_outbox"] == 0


def test_budget_context_integration(client: TestClient, outbox: list) -> None:
    auth(client, outbox)

    # Cria uma divisão no Meu Orçamento para testar comunicação entre soluções.
    split_res = client.post(
        "/api/splits",
        json={
            "person": "Lucas",
            "description": "Jantar",
            "amount": "85.50",
            "direction": "owes_me",
        },
    )
    assert split_res.status_code == 201, split_res.text

    chat = client.post(
        "/api/messaging/chats",
        json={"phone": "5511966665555", "name": "Lucas", "budget_person": "Lucas"},
    ).json()

    ctx = client.get("/api/messaging/budget-context", params={"chat_id": chat["id"]})
    assert ctx.status_code == 200, ctx.text
    data = ctx.json()
    assert "month" in data
    assert "balance" in data
    assert any(c["person"] == "Lucas" and c["owes_me"] == "85.50" for c in data["contacts"])
    assert data["linked_contact"]["person"] == "Lucas"
    assert data["linked_contact"]["net"] == "85.50"


def test_budget_context_counts_partial_loan_installment_balance(
    client: TestClient, outbox: list, db: Session
) -> None:
    from datetime import date
    from decimal import Decimal

    from app.models import LoanInstallment, PersonalLoan, User

    auth(client, outbox)
    user = db.query(User).first()
    assert user is not None
    loan = PersonalLoan(
        user_id=user.id,
        person="Duda",
        description="Empréstimo teste",
        principal=Decimal("1000.00"),
        direction="owes_me",
        mode="none",
        frequency="week",
        count=2,
        rate=Decimal("0"),
        first_due=date(2026, 11, 1),
    )
    db.add(loan)
    db.flush()
    # Parcela 1 em aberto inteira (262,50) + parcela 2 paga parcialmente (100 de 262,50 → 162,50).
    db.add_all(
        [
            LoanInstallment(
                loan_id=loan.id,
                number=1,
                due_date=date(2026, 11, 1),
                amount=Decimal("262.50"),
                interest=Decimal("0"),
                principal_part=Decimal("262.50"),
            ),
            LoanInstallment(
                loan_id=loan.id,
                number=2,
                due_date=date(2026, 11, 8),
                amount=Decimal("262.50"),
                interest=Decimal("0"),
                principal_part=Decimal("262.50"),
                received_at=date(2026, 11, 2),
                received_amount=Decimal("100.00"),
            ),
        ]
    )
    db.commit()

    chat = client.post(
        "/api/messaging/chats",
        json={"phone": "5511977771111", "name": "Duda", "budget_person": "Duda"},
    ).json()
    ctx = client.get("/api/messaging/budget-context", params={"chat_id": chat["id"]}).json()
    assert ctx["linked_contact"]["net"] == "425.00"


# ---------------------------------------------------------------- cliente HTTP do conector


class _FakeResponse:
    def __init__(self, status: int = 202) -> None:
        self.status = status

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


def _configure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "messaging_connector_url", CONNECTOR_URL + "/")
    monkeypatch.setattr(get_settings(), "messaging_connector_token", TOKEN)


def test_connector_client_sends_token_json_and_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(monkeypatch)
    seen: list = []

    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        seen.append((request, timeout))
        return _FakeResponse(202)

    monkeypatch.setattr(connector_client.urllib.request, "urlopen", fake_urlopen)
    session_id = uuid.uuid4()
    connector_client.start_session(session_id)
    assert connector_client.stop_session(session_id, logout=True) is True
    assert connector_client.mark_read(session_id, "1@s.whatsapp.net", ["A"]) is True

    request, timeout = seen[0]
    assert timeout == 3
    assert request.full_url == f"{CONNECTOR_URL}/sessions/{session_id}/start"
    assert request.get_method() == "POST"
    assert request.get_header("X-connector-token") == TOKEN
    assert request.get_header("Content-type") == "application/json"
    assert json.loads(seen[1][0].data) == {"logout": True}
    assert json.loads(seen[2][0].data) == {"remote_jid": "1@s.whatsapp.net", "external_ids": ["A"]}


def test_connector_client_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = uuid.uuid4()
    called: list = []

    def refuse(request, timeout):  # type: ignore[no-untyped-def]
        called.append(request)
        raise urllib.error.URLError("conexão recusada")

    monkeypatch.setattr(connector_client.urllib.request, "urlopen", refuse)
    # Sem configuração: o início falha e o resto nem tenta a rede.
    with pytest.raises(connector_client.ConnectorError):
        connector_client.start_session(session_id)
    assert connector_client.flush_session(session_id) is False
    assert called == []

    _configure(monkeypatch)
    with pytest.raises(connector_client.ConnectorError):
        connector_client.start_session(session_id)
    assert connector_client.flush_session(session_id) is False
    assert len(called) == 2

    def server_error(request, timeout):  # type: ignore[no-untyped-def]
        raise urllib.error.HTTPError(request.full_url, 500, "erro", {}, None)  # type: ignore[arg-type]

    monkeypatch.setattr(connector_client.urllib.request, "urlopen", server_error)
    with pytest.raises(connector_client.ConnectorError):
        connector_client.start_session(session_id)

    def timeout_error(request, timeout):  # type: ignore[no-untyped-def]
        raise TimeoutError("tempo esgotado")

    monkeypatch.setattr(connector_client.urllib.request, "urlopen", timeout_error)
    assert connector_client.stop_session(session_id, logout=False) is False


def test_chat_credit_purchase_uses_invoice_and_never_enters_paid(
    client: TestClient, outbox: list, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import date
    from decimal import Decimal

    from sqlalchemy import select

    from app.models import CreditCard, Expense, User
    from app.services import cards
    from app.services.messaging import budget as bridge

    auth(client, outbox)
    user = db.scalar(select(User))
    assert user is not None
    card = CreditCard(
        user_id=user.id,
        name="Crédito teste",
        kind="credit",
        limit_amount=Decimal("5000"),
        closing_day=10,
        due_day=20,
    )
    db.add(card)
    db.commit()
    purchase = date(2026, 11, 20)
    monkeypatch.setattr(bridge, "today_local", lambda: purchase)
    chat = client.post("/api/messaging/chats", json={"phone": "5511966665555"}).json()
    ctx = client.get("/api/messaging/budget-context").json()
    assert {"id": str(card.id), "name": card.name} in ctx["cards"]
    body = {
        "description": "Compra no chat",
        "amount": "1234.56",
        "payment_method": "credit",
        "paid": True,
    }
    missing = client.post(f"/api/messaging/chats/{chat['id']}/budget-entry", json=body)
    assert missing.status_code == 400
    assert missing.json()["error"] == "card_required"
    body["card_id"] = str(card.id)
    res = client.post(f"/api/messaging/chats/{chat['id']}/budget-entry", json=body)
    assert res.status_code == 201, res.text
    db.expire_all()
    expense = db.get(Expense, uuid.UUID(res.json()["id"]))
    assert expense is not None
    expected_due = cards.installment_dates(card, purchase, 1)[0]
    assert expense.card_id == card.id
    assert expense.paid is False and expense.paid_at is None
    assert expense.due_date == expected_due
    assert expense.month == expected_due.replace(day=1)
    assert res.json()["month"] == expense.month.strftime("%Y-%m")
    assert cards.summary(db, user, purchase)[0]["used"] == Decimal("1234.56")


@pytest.mark.parametrize("amount", ["0", "0.001", "-1", "10000000000", "1e100", "NaN", "Infinity"])
def test_chat_budget_rejects_invalid_amounts(client: TestClient, outbox: list, amount: str) -> None:
    auth(client, outbox)
    chat = client.post("/api/messaging/chats", json={"phone": "5511966665555"}).json()
    res = client.post(
        f"/api/messaging/chats/{chat['id']}/budget-entry",
        json={"description": "Inválido", "amount": amount},
    )
    assert res.status_code == 422, res.text


def test_chat_budget_rejects_unknown_payment_method(client: TestClient, outbox: list) -> None:
    auth(client, outbox)
    chat = client.post("/api/messaging/chats", json={"phone": "5511966665555"}).json()
    res = client.post(
        f"/api/messaging/chats/{chat['id']}/budget-entry",
        json={"description": "Inválido", "amount": "1", "payment_method": "desconhecido"},
    )
    assert res.status_code == 422


def test_quick_replies_deleted_defaults_stay_deleted_and_duplicate_is_rejected(
    client: TestClient, outbox: list
) -> None:
    auth(client, outbox)
    defaults = client.get("/api/messaging/quick-replies").json()
    assert len(defaults) == 5
    for reply in defaults:
        assert client.delete(f"/api/messaging/quick-replies/{reply['id']}").status_code == 204
    assert client.get("/api/messaging/quick-replies").json() == []
    body = {"shortcut": "agenda", "title": "Agenda", "body": "Texto original"}
    first = client.post("/api/messaging/quick-replies", json=body)
    assert first.status_code == 201, first.text
    duplicate = client.post("/api/messaging/quick-replies", json={**body, "body": "Troca indevida"})
    assert duplicate.status_code == 409
    assert duplicate.json()["error"] == "quick_reply_exists"
    assert client.get("/api/messaging/quick-replies").json()[0]["body"] == "Texto original"


def test_budget_context_loan_without_received_amount_matches_splits_and_client_ref_dedup(
    client: TestClient, outbox: list, db: Session
) -> None:
    from datetime import date
    from decimal import Decimal

    from app.models import Expense, Income, LoanInstallment, PersonalLoan, User
    from app.services import splits

    auth(client, outbox)
    user = db.query(User).first()
    assert user is not None
    loan = PersonalLoan(
        user_id=user.id,
        person="Beto",
        description="Empréstimo B5",
        principal=Decimal("200.00"),
        direction="owes_me",
        mode="none",
        frequency="month",
        count=1,
        rate=Decimal("0"),
        first_due=date(2026, 11, 5),
    )
    db.add(loan)
    db.flush()
    # received_at preenchido mas received_amount None: Divisões e Mensageria concordam (200.00).
    db.add(
        LoanInstallment(
            loan_id=loan.id,
            number=1,
            due_date=date(2026, 11, 5),
            amount=Decimal("200.00"),
            interest=Decimal("0"),
            principal_part=Decimal("200.00"),
            received_at=date(2026, 11, 6),
            received_amount=None,
        )
    )
    db.commit()

    board = splits.board(db, user)
    chat = client.post(
        "/api/messaging/chats",
        json={"phone": "5511988881111", "name": "Beto", "budget_person": "Beto"},
    ).json()
    ctx = client.get("/api/messaging/budget-context", params={"chat_id": chat["id"]}).json()
    assert ctx["linked_contact"]["net"] == str(board["owed_to_me"]) == "200.00"

    # B3: client_ref evita duplicidade ao clicar duas vezes no Lançar (mês novo).
    ref_inc = str(uuid.uuid4())
    r1 = client.post(
        f"/api/messaging/chats/{chat['id']}/budget-entry",
        json={"kind": "income", "description": "Freela", "amount": "500.00", "client_ref": ref_inc},
    )
    r2 = client.post(
        f"/api/messaging/chats/{chat['id']}/budget-entry",
        json={"kind": "income", "description": "Freela", "amount": "500.00", "client_ref": ref_inc},
    )
    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]
    assert db.query(Income).filter(Income.user_id == user.id).count() == 1

    ref_exp = str(uuid.uuid4())
    e1 = client.post(
        f"/api/messaging/chats/{chat['id']}/budget-entry",
        json={
            "kind": "expense",
            "description": "Material",
            "amount": "80.00",
            "client_ref": ref_exp,
        },
    )
    e2 = client.post(
        f"/api/messaging/chats/{chat['id']}/budget-entry",
        json={
            "kind": "expense",
            "description": "Material",
            "amount": "80.00",
            "client_ref": ref_exp,
        },
    )
    assert e1.status_code == 201 and e2.status_code == 201
    assert e1.json()["id"] == e2.json()["id"]
    assert db.query(Expense).filter(Expense.user_id == user.id).count() == 1


def test_messaging_bridges_blocked_and_pdf_send_quota(
    client: TestClient, outbox: list, db: Session
) -> None:
    from sqlalchemy import select

    from app.models import MessagingSession, StoredFile, User
    from tests.conftest import create_verified_user, login

    create_verified_user(client, outbox, "adm-msg-c4@example.com")
    adm = db.scalar(select(User).where(User.email == "adm-msg-c4@example.com"))
    assert adm is not None
    adm.is_admin = True
    db.commit()

    create_verified_user(client, outbox, "user-msg-c4@example.com")
    dono = db.scalar(select(User).where(User.email == "user-msg-c4@example.com"))
    assert dono is not None

    assert login(client, dono.email).status_code == 200
    chat = client.post("/api/messaging/chats", json={"phone": "5511966664444"}).json()
    db.add(MessagingSession(user_id=dono.id, status="ready", wanted=True))
    doc = client.post(
        "/api/proposals",
        json={
            "doc_type": "proposal",
            "customer_name": "Cliente Cota",
            "items": [{"name": "Item", "qty": 1, "unit_price": "100.00"}],
        },
    ).json()

    # Cota de arquivos cheia não bloqueia a Mensageria (decisão D4 de 21/11/2026): a mídia
    # enviada vai para o teto próprio das mídias e não conta na cota de arquivos.
    dono.storage_quota_mb = 5
    db.add(
        StoredFile(
            owner_id=dono.id,
            purpose="attachment",
            filename="cheio.bin",
            content_type="application/octet-stream",
            size=5 * 1024 * 1024 - 10,
            width=0,
            height=0,
            data=b"x",
        )
    )
    db.commit()
    files_before = admin_service.user_storage_bytes(db, dono.id)
    quota_send = client.post(
        f"/api/proposals/{doc['id']}/send-messaging",
        json={"chat_id": chat["id"]},
    )
    assert quota_send.status_code < 300, quota_send.text
    assert admin_service.user_storage_bytes(db, dono.id) == files_before
    assert media_service.media_bytes(db, dono.id) > 0

    # C4: bloqueio em meu-orcamento e dashboard-crm impede pontes via Mensageria.
    assert login(client, adm.email).status_code == 200
    assert (
        client.patch(
            f"/api/admin/users/{dono.id}/permissions",
            json={"blocked_resources": ["meu-orcamento", "dashboard-crm"], "storage_quota_mb": 50},
        ).status_code
        == 200
    )
    assert login(client, dono.email).status_code == 200
    assert client.get("/api/messaging/budget-context").status_code == 403
    assert (
        client.post(
            f"/api/messaging/chats/{chat['id']}/budget-entry",
            json={"kind": "expense", "description": "Teste", "amount": "10.00"},
        ).status_code
        == 403
    )
    assert client.get(f"/api/messaging/chats/{chat['id']}/crm-context").status_code == 403
    assert (
        client.post(
            f"/api/messaging/chats/{chat['id']}/crm-deal",
            json={"title": "Bloqueado", "value": "100.00"},
        ).status_code
        == 403
    )
