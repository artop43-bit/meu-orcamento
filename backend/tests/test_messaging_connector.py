"""Testes da API usada pelo conector do WhatsApp: chave, sessões, fila e eventos."""

import importlib.util
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.types import utcnow
from app.services.messaging import connector as connector_service
from tests.messaging_helpers import (
    TOKEN,
    FakeConnector,
    auth,
    chat_rows,
    claim,
    connect_ready,
    connector_headers,
    inbound,
    install_fake_connector,
    message_row,
    send_events,
    session_row,
)

PN = "5511977776666@s.whatsapp.net"
LID = "123456789012345@lid"


@pytest.fixture
def connector(monkeypatch: pytest.MonkeyPatch) -> FakeConnector:
    return install_fake_connector(monkeypatch)


def _block(db: Session, email: str) -> None:
    from sqlalchemy import select

    from app.models import User

    db.expire_all()
    user = db.scalar(select(User).where(User.email == email))
    assert user is not None
    user.access_status = "blocked"
    db.commit()


def _send_and_claim(client: TestClient, session_id: str, chat_id: str, body: str) -> dict:
    sent = client.post(f"/api/messaging/chats/{chat_id}/messages", json={"body": body})
    assert sent.status_code == 201, sent.text
    items = claim(client, session_id)
    assert [i["message_id"] for i in items] == [sent.json()["id"]]
    return items[0]


# ---------------------------------------------------------------- chave do conector


def test_connector_token(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "messaging_connector_token", "")
    # Sem chave configurada na API: recurso indisponível.
    res = client.get("/api/messaging/connector/sessions", headers=connector_headers())
    assert res.status_code == 503
    assert res.json()["error"] == "connector_unavailable"

    monkeypatch.setattr(get_settings(), "messaging_connector_token", TOKEN)
    assert client.get("/api/messaging/connector/sessions").status_code == 401
    wrong = client.get(
        "/api/messaging/connector/sessions", headers=connector_headers("chave-errada")
    )
    assert wrong.status_code == 401
    assert wrong.json()["error"] == "connector_unauthorized"

    ok = client.get("/api/messaging/connector/sessions", headers=connector_headers())
    assert ok.status_code == 200
    assert ok.json() == {"sessions": []}

    # O conector posta sem o cabeçalho da tela (CSRF liberado só com a chave).
    posted = client.post(
        "/api/messaging/connector/events", json={"events": []}, headers=connector_headers()
    )
    assert posted.status_code == 200
    assert posted.json() == {"processed": 0, "ignored": 0}
    blocked = client.post(
        "/api/messaging/connector/events",
        json={"events": []},
        headers={"X-Requested-With": ""},
    )
    assert blocked.status_code == 403
    assert blocked.json()["error"] == "csrf"


def test_sessions_list_only_wanted_and_not_blocked(
    client: TestClient, outbox: list, db: Session, connector: FakeConnector
) -> None:
    auth(client, outbox, "ana@example.com")
    ana = connect_ready(client, db)
    client.post("/api/auth/logout")
    auth(client, outbox, "bruno@example.com")
    client.get("/api/messaging/session")  # sessão criada, mas sem pedir conexão
    client.post("/api/auth/logout")
    auth(client, outbox, "carla@example.com")
    assert client.post("/api/messaging/session/connect").status_code == 200

    res = client.get("/api/messaging/connector/sessions", headers=connector_headers())
    carla = str(session_row(db, "carla@example.com").id)
    assert [s["session_id"] for s in res.json()["sessions"]] == [ana, carla]

    _block(db, "carla@example.com")
    res = client.get("/api/messaging/connector/sessions", headers=connector_headers())
    assert [s["session_id"] for s in res.json()["sessions"]] == [ana]


# ---------------------------------------------------------------- fila de envio


def test_outbox_claim(
    client: TestClient, outbox: list, db: Session, connector: FakeConnector
) -> None:
    auth(client, outbox)
    session_id = connect_ready(client, db)
    send_events(client, inbound(session_id, "IN-1", PN, "Pode mandar o resumo?"))
    incoming = message_row(db, external_id="IN-1")
    chat_id = str(incoming.chat_id)

    sent = client.post(
        f"/api/messaging/chats/{chat_id}/messages",
        json={"body": "Claro!", "reply_to_id": str(incoming.id)},
    ).json()
    items = claim(client, session_id)
    assert len(items) == 1
    item = items[0]
    assert item["message_id"] == sent["id"]
    assert item["session_id"] == session_id
    assert item["remote_jid"] == PN
    assert item["body"] == "Claro!"
    assert item["quoted"] == {
        "external_id": "IN-1",
        "from_me": False,
        "remote_jid": PN,
        "body": "Pode mandar o resumo?",
    }
    assert message_row(db, id=uuid.UUID(sent["id"])).claimed_at is not None

    # Reservado: não sai de novo dentro de 60 s.
    assert claim(client, session_id) == []
    # Sem resposta do conector por mais de 60 s: volta para a fila.
    row = message_row(db, id=uuid.UUID(sent["id"]))
    row.claimed_at = utcnow() - timedelta(seconds=61)
    db.commit()
    assert [i["message_id"] for i in claim(client, session_id)] == [sent["id"]]

    # Só sessões pedidas, prontas e mantidas conectadas.
    second = client.post(f"/api/messaging/chats/{chat_id}/messages", json={"body": "Dois"}).json()
    assert claim(client, str(uuid.uuid4())) == []
    session = session_row(db)
    session.status = "qr"
    db.commit()
    assert claim(client, session_id) == []
    session = session_row(db)
    session.status = "ready"
    session.wanted = False
    db.commit()
    assert claim(client, session_id) == []
    session = session_row(db)
    session.wanted = True
    db.commit()
    assert [i["message_id"] for i in claim(client, session_id, limit=5)] == [second["id"]]

    # Identificadores inválidos ou demais.
    bad = client.get(
        "/api/messaging/connector/outbox",
        params={"session_ids": "nao-e-uuid"},
        headers=connector_headers(),
    )
    assert bad.status_code == 400
    many = ",".join(str(uuid.uuid4()) for _ in range(201))
    too_many = client.get(
        "/api/messaging/connector/outbox",
        params={"session_ids": many},
        headers=connector_headers(),
    )
    assert too_many.status_code == 400
    assert claim(client) == []


def test_outbox_skips_blocked_users_and_orders_by_creation(
    client: TestClient, outbox: list, db: Session, connector: FakeConnector
) -> None:
    auth(client, outbox)
    session_id = connect_ready(client, db)
    chat = client.post("/api/messaging/chats", json={"phone": "5511991112222"}).json()
    ids = [
        client.post(f"/api/messaging/chats/{chat['id']}/messages", json={"body": f"M{n}"}).json()[
            "id"
        ]
        for n in range(3)
    ]
    assert [i["message_id"] for i in claim(client, session_id, limit=2)] == ids[:2]
    _block(db, "ana@example.com")
    assert claim(client, session_id) == []


# ---------------------------------------------------------------- eventos de status


def test_status_events(
    client: TestClient, outbox: list, db: Session, connector: FakeConnector
) -> None:
    auth(client, outbox)
    client.post("/api/messaging/session/connect")
    sid = str(session_row(db).id)

    assert (
        send_events(client, {"type": "status", "session_id": sid, "status": "qr", "qr": "Q1"})[
            "processed"
        ]
        == 1
    )
    assert client.get("/api/messaging/session").json()["qr_code"] == "Q1"

    send_events(
        client,
        {
            "type": "status",
            "session_id": sid,
            "status": "ready",
            "wa_jid": "5511988887777:12@s.whatsapp.net",
            "display_name": "Ana",
        },
    )
    summary = client.get("/api/messaging/session").json()
    assert summary["status"] == "ready"
    assert summary["connected"] is True
    assert summary["qr_code"] is None
    assert summary["last_error"] is None
    # Sem "phone" no evento: o número sai do JID do próprio aparelho.
    assert summary["phone"] == "5511988887777"
    assert summary["display_name"] == "Ana"
    assert summary["last_seen_at"] is not None
    assert session_row(db).wa_jid == "5511988887777:12@s.whatsapp.net"

    # Erro de conexão (ex.: número conectado em outro lugar).
    send_events(
        client,
        {
            "type": "status",
            "session_id": sid,
            "status": "error",
            "error": "Este número foi conectado em outro lugar.",
        },
    )
    summary = client.get("/api/messaging/session").json()
    assert summary["status"] == "error"
    assert summary["last_error"] == "Este número foi conectado em outro lugar."

    # Saiu pelo celular: a API deixa de pedir a conexão.
    send_events(
        client,
        {
            "type": "status",
            "session_id": sid,
            "status": "disconnected",
            "wanted": False,
            "error": "O WhatsApp foi desconectado pelo celular.",
        },
    )
    summary = client.get("/api/messaging/session").json()
    assert summary["status"] == "disconnected"
    assert summary["last_error"] == "O WhatsApp foi desconectado pelo celular."
    assert session_row(db).wanted is False

    # Evento atrasado de um pedido antigo: ignorado.
    stale = send_events(
        client,
        {"type": "status", "session_id": sid, "status": "qr", "qr": "Q-velho"},
        {"type": "status", "session_id": sid, "status": "ready"},
        {"type": "status", "session_id": sid, "status": "connecting"},
    )
    assert stale == {"processed": 0, "ignored": 3}
    assert client.get("/api/messaging/session").json()["status"] == "disconnected"


# ---------------------------------------------------------------- mensagens recebidas


def test_message_event_creates_chat_and_dedups(
    client: TestClient, outbox: list, db: Session, connector: FakeConnector
) -> None:
    auth(client, outbox)
    sid = connect_ready(client, db)

    result = send_events(
        client,
        inbound(sid, "ABC", PN, "Olá!", push_name="Fernanda"),
        inbound(sid, "ABC", PN, "Olá!", push_name="Fernanda"),
    )
    assert result == {"processed": 1, "ignored": 1}
    chats = client.get("/api/messaging/chats").json()
    assert len(chats) == 1
    chat = chats[0]
    assert chat["name"] == "Fernanda"
    assert chat["phone"] == "5511977776666"
    assert chat["remote_jid"] == PN
    assert chat["unread_count"] == 1
    assert chat["last_message_preview"] == "Olá!"
    assert chat["last_message_at"].startswith("2030-01-10T12:00:00")

    msg = message_row(db, external_id="ABC")
    assert msg.direction == "in"
    assert msg.status == "delivered"
    assert msg.message_type == "chat"
    assert msg.created_at.isoformat().startswith("2030-01-10T12:00:00")

    # Mídia já vem descrita pelo conector; tipo desconhecido vira "other".
    send_events(
        client,
        inbound(sid, "IMG", PN, "📷 Foto · recibo", message_type="image"),
        inbound(sid, "ODD", PN, "", message_type="enquete"),
    )
    assert message_row(db, external_id="IMG").message_type == "image"
    odd = message_row(db, external_id="ODD")
    assert odd.message_type == "other"
    assert odd.body == "Mensagem não suportada"

    # Grupos, status e canais não viram conversa.
    ignored = send_events(
        client,
        inbound(sid, "G1", "120363000000000000@g.us"),
        inbound(sid, "S1", "status@broadcast"),
    )
    assert ignored == {"processed": 0, "ignored": 2}


def test_message_from_me_history_and_preview(
    client: TestClient, outbox: list, db: Session, connector: FakeConnector
) -> None:
    auth(client, outbox)
    sid = connect_ready(client, db)

    send_events(
        client,
        inbound(
            sid, "H1", PN, "Antiga do histórico", history=True, timestamp="2030-01-01T10:00:00Z"
        ),
        inbound(
            sid,
            "ME1",
            PN,
            "Mandei pelo celular",
            from_me=True,
            push_name="Ana",
            timestamp="2030-01-02T10:00:00Z",
        ),
    )
    chat = client.get("/api/messaging/chats").json()[0]
    # Histórico e as minhas não contam como não lidas; o nome não vira o meu.
    assert chat["unread_count"] == 0
    assert chat["name"] == "+55 (11) 97777-6666"
    assert chat["last_message_preview"] == "Mandei pelo celular"
    mine = message_row(db, external_id="ME1")
    assert mine.direction == "out"
    assert mine.status == "sent"

    # Arquivada: uma nova recebida desarquiva; uma antiga não muda a prévia.
    client.patch(f"/api/messaging/chats/{chat['id']}", json={"archived": True})
    send_events(
        client,
        inbound(sid, "OLD", PN, "Bem antiga", history=True, timestamp="2029-12-01T10:00:00Z"),
    )
    archived = client.get("/api/messaging/chats", params={"filter": "archived"}).json()
    assert [c["id"] for c in archived] == [chat["id"]]
    assert archived[0]["last_message_preview"] == "Mandei pelo celular"

    send_events(
        client,
        inbound(
            sid, "NEW", PN, "Oi de novo", push_name="Fernanda", timestamp="2030-01-03T10:00:00Z"
        ),
    )
    chat = client.get(f"/api/messaging/chats/{chat['id']}").json()
    assert chat["archived"] is False
    assert chat["unread_count"] == 1
    assert chat["last_message_preview"] == "Oi de novo"
    # O nome era o número formatado: troca pelo nome do WhatsApp.
    assert chat["name"] == "Fernanda"

    # Nome escolhido pela pessoa não é trocado.
    client.patch(f"/api/messaging/chats/{chat['id']}", json={"name": "Fê"})
    send_events(client, inbound(sid, "NEW2", PN, "Oi", push_name="Fernanda Souza"))
    assert client.get(f"/api/messaging/chats/{chat['id']}").json()["name"] == "Fê"


def test_message_quoted_reply(
    client: TestClient, outbox: list, db: Session, connector: FakeConnector
) -> None:
    auth(client, outbox)
    sid = connect_ready(client, db)
    send_events(
        client,
        inbound(sid, "Q1", PN, "Quanto ficou o jantar?"),
        inbound(sid, "Q2", PN, "Respondendo", quoted_external_id="Q1"),
        inbound(sid, "Q3", PN, "Citação perdida", quoted_external_id="NAO-EXISTE"),
    )
    original = message_row(db, external_id="Q1")
    assert message_row(db, external_id="Q2").reply_to_id == original.id
    assert message_row(db, external_id="Q3").reply_to_id is None
    page = client.get(f"/api/messaging/chats/{original.chat_id}/messages").json()
    reply = next(m for m in page["items"] if m["external_id"] == "Q2")
    assert reply["reply_preview"] == "Quanto ficou o jantar?"


def test_lid_and_phone_resolution_and_merge(
    client: TestClient, outbox: list, db: Session, connector: FakeConnector
) -> None:
    auth(client, outbox)
    sid = connect_ready(client, db)

    # Contato com número escondido: conversa só com LID.
    send_events(client, inbound(sid, "L1", LID, "Oi, sou eu", push_name="Fernanda"))
    lid_chat = client.get("/api/messaging/chats").json()[0]
    assert lid_chat["remote_jid"] == LID
    assert lid_chat["lid_jid"] == LID
    assert lid_chat["phone"] is None
    assert lid_chat["phone_display"] == ""
    assert lid_chat["name"] == "Fernanda"

    # A pessoa abriu a mesma conversa pelo número na tela (outra conversa, por enquanto).
    by_phone = client.post(
        "/api/messaging/chats", json={"phone": "11977776666", "notes": "Vizinha"}
    ).json()
    assert by_phone["id"] != lid_chat["id"]

    # Chega mensagem com os dois JIDs: as duas conversas viram uma só (a do número).
    send_events(
        client,
        inbound(
            sid,
            "L2",
            LID,
            "Agora com número",
            remote_jid_alt=PN,
            push_name="Fê",
            timestamp="2030-01-10T12:01:00Z",
        ),
    )
    chats = client.get("/api/messaging/chats").json()
    assert len(chats) == 1
    merged = chats[0]
    assert merged["id"] == by_phone["id"]
    assert merged["remote_jid"] == PN
    assert merged["lid_jid"] == LID
    assert merged["phone"] == "5511977776666"
    assert merged["notes"] == "Vizinha"
    assert merged["unread_count"] == 2
    # O nome que veio do WhatsApp na conversa antiga vale mais que o número formatado.
    assert merged["name"] == "Fernanda"
    page = client.get(f"/api/messaging/chats/{merged['id']}/messages").json()
    assert [m["external_id"] for m in page["items"]] == ["L1", "L2"]
    assert client.get(f"/api/messaging/chats/{lid_chat['id']}").status_code == 404

    # Só pelo LID, depois de juntar, continua achando a mesma conversa.
    send_events(client, inbound(sid, "L3", LID, "Só LID de novo"))
    assert [c["id"] for c in client.get("/api/messaging/chats").json()] == [merged["id"]]


def test_lid_chat_learns_phone(
    client: TestClient, outbox: list, db: Session, connector: FakeConnector
) -> None:
    auth(client, outbox)
    sid = connect_ready(client, db)
    send_events(client, inbound(sid, "X1", LID, "Oi"))
    chat = client.get("/api/messaging/chats").json()[0]
    assert chat["name"] == "Contato do WhatsApp"

    # O número aparece (alt): a conversa passa a usar o número para enviar.
    send_events(client, inbound(sid, "X2", PN, "Oi de novo", remote_jid_alt=LID))
    same = client.get(f"/api/messaging/chats/{chat['id']}").json()
    assert same["remote_jid"] == PN
    assert same["lid_jid"] == LID
    assert same["phone"] == "5511977776666"
    assert same["name"] == "+55 (11) 97777-6666"
    assert len(chat_rows(db)) == 1


# ---------------------------------------------------------------- confirmações


def test_ack_and_receipts(
    client: TestClient, outbox: list, db: Session, connector: FakeConnector
) -> None:
    auth(client, outbox)
    sid = connect_ready(client, db)
    chat = client.post("/api/messaging/chats", json={"phone": "5511977776666"}).json()
    item = _send_and_claim(client, sid, chat["id"], "Oi")
    message_id = item["message_id"]

    assert send_events(
        client,
        {
            "type": "ack",
            "session_id": sid,
            "message_id": message_id,
            "status": "sent",
            "external_id": "OUT-1",
        },
    ) == {"processed": 1, "ignored": 0}
    msg = message_row(db, id=uuid.UUID(message_id))
    assert msg.status == "sent"
    assert msg.external_id == "OUT-1"
    assert msg.sent_at is not None
    assert msg.claimed_at is None
    assert claim(client, sid) == []

    def receipt(status: str, **extra: Any) -> dict[str, Any]:
        return {
            "type": "receipt",
            "session_id": sid,
            "external_id": "OUT-1",
            "status": status,
            **extra,
        }

    before = message_row(db, id=uuid.UUID(message_id)).updated_at
    assert send_events(client, receipt("delivered"))["processed"] == 1
    after = message_row(db, id=uuid.UUID(message_id))
    assert after.status == "delivered"
    assert after.updated_at > before
    # Nunca volta atrás; "played" (áudio ouvido) vale como lida; falha depois de entregue não vale.
    assert send_events(client, receipt("sent")) == {"processed": 0, "ignored": 1}
    assert send_events(client, receipt("failed")) == {"processed": 0, "ignored": 1}
    assert message_row(db, id=uuid.UUID(message_id)).status == "delivered"
    assert send_events(client, receipt("played"))["processed"] == 1
    assert message_row(db, id=uuid.UUID(message_id)).status == "read"
    assert send_events(client, receipt("delivered"), receipt("read")) == {
        "processed": 0,
        "ignored": 2,
    }
    # Confirmação de mensagem desconhecida.
    unknown = send_events(client, {**receipt("read"), "external_id": "NAO-EXISTE"})
    assert unknown == {"processed": 0, "ignored": 1}

    # Envio que falhou: fica com o motivo.
    item2 = _send_and_claim(client, sid, chat["id"], "Segunda")
    send_events(
        client,
        {
            "type": "ack",
            "session_id": sid,
            "message_id": item2["message_id"],
            "status": "failed",
            "error": "Número sem WhatsApp.",
        },
    )
    failed = message_row(db, id=uuid.UUID(item2["message_id"]))
    assert failed.status == "failed"
    assert failed.error_detail == "Número sem WhatsApp."
    assert failed.claimed_at is None
    assert claim(client, sid) == []

    # Enviada mas recusada depois (ainda não entregue): falha vale.
    item3 = _send_and_claim(client, sid, chat["id"], "Terceira")
    send_events(
        client,
        {
            "type": "ack",
            "session_id": sid,
            "message_id": item3["message_id"],
            "status": "sent",
            "external_id": "OUT-3",
        },
        {"type": "receipt", "session_id": sid, "external_id": "OUT-3", "status": "failed"},
    )
    third = message_row(db, id=uuid.UUID(item3["message_id"]))
    assert third.status == "failed"
    assert third.error_detail

    page = client.get(f"/api/messaging/chats/{chat['id']}/messages").json()
    assert [m["status"] for m in page["items"]] == ["read", "failed", "failed"]


def test_ack_replaces_echo_of_same_message(
    client: TestClient, outbox: list, db: Session, connector: FakeConnector
) -> None:
    auth(client, outbox)
    sid = connect_ready(client, db)
    chat = client.post("/api/messaging/chats", json={"phone": "5511977776666"}).json()
    item = _send_and_claim(client, sid, chat["id"], "Oi")
    # O WhatsApp devolveu a própria mensagem como evento antes da confirmação.
    send_events(client, inbound(sid, "ECO-1", PN, "Oi", from_me=True))
    send_events(
        client,
        {
            "type": "ack",
            "session_id": sid,
            "message_id": item["message_id"],
            "status": "sent",
            "external_id": "ECO-1",
        },
    )
    page = client.get(f"/api/messaging/chats/{chat['id']}/messages").json()
    assert [(m["id"], m["external_id"]) for m in page["items"]] == [(item["message_id"], "ECO-1")]


def test_ack_echo_keeps_replies_pointing_to_queue_message(
    client: TestClient, outbox: list, db: Session, connector: FakeConnector
) -> None:
    auth(client, outbox)
    sid = connect_ready(client, db)
    chat = client.post("/api/messaging/chats", json={"phone": "5511977776666"}).json()
    item = _send_and_claim(client, sid, chat["id"], "Pode ser às 18h?")
    # O eco chega antes da confirmação e o contato já responde citando o eco.
    send_events(
        client,
        inbound(sid, "ECO-2", PN, "Pode ser às 18h?", from_me=True),
        inbound(sid, "RESP-1", PN, "Pode sim", quoted_external_id="ECO-2"),
    )
    answer = message_row(db, external_id="RESP-1")
    answered_at = answer.updated_at
    send_events(
        client,
        {
            "type": "ack",
            "session_id": sid,
            "message_id": item["message_id"],
            "status": "sent",
            "external_id": "ECO-2",
        },
    )
    answer = message_row(db, external_id="RESP-1")
    assert answer.reply_to_id == uuid.UUID(item["message_id"])
    assert answer.updated_at > answered_at
    page = client.get(f"/api/messaging/chats/{chat['id']}/messages").json()
    reply = next(m for m in page["items"] if m["external_id"] == "RESP-1")
    assert reply["reply_preview"] == "Pode ser às 18h?"


def test_ack_failed_after_sent_only_releases_claim(
    client: TestClient, outbox: list, db: Session, connector: FakeConnector
) -> None:
    auth(client, outbox)
    sid = connect_ready(client, db)
    chat = client.post("/api/messaging/chats", json={"phone": "5511977776666"}).json()
    item = _send_and_claim(client, sid, chat["id"], "Oi")
    send_events(
        client,
        {
            "type": "ack",
            "session_id": sid,
            "message_id": item["message_id"],
            "status": "sent",
            "external_id": "OUT-9",
        },
    )
    # Uma tentativa repetida falhou, mas a mensagem já tinha saído: continua enviada.
    msg = message_row(db, id=uuid.UUID(item["message_id"]))
    msg.claimed_at = utcnow()
    db.commit()
    result = send_events(
        client,
        {
            "type": "ack",
            "session_id": sid,
            "message_id": item["message_id"],
            "status": "failed",
            "error": "Tempo esgotado.",
        },
    )
    assert result == {"processed": 1, "ignored": 0}
    msg = message_row(db, id=uuid.UUID(item["message_id"]))
    assert msg.status == "sent"
    assert msg.error_detail is None
    assert msg.claimed_at is None


def test_claim_and_changes_bump_updated_at(
    client: TestClient, outbox: list, db: Session, connector: FakeConnector
) -> None:
    auth(client, outbox)
    sid = connect_ready(client, db)
    send_events(client, inbound(sid, "IN-9", PN, "Oi"))
    chat_id = str(message_row(db, external_id="IN-9").chat_id)
    sent = client.post(f"/api/messaging/chats/{chat_id}/messages", json={"body": "Oi!"}).json()
    created = message_row(db, id=uuid.UUID(sent["id"])).updated_at

    # Reservar o item da fila também é uma alteração (a tela sincroniza por updated_at).
    assert [i["message_id"] for i in claim(client, sid)] == [sent["id"]]
    claimed = message_row(db, id=uuid.UUID(sent["id"]))
    assert claimed.claimed_at is not None
    assert claimed.updated_at > created

    # Confirmação de leitura só vale para mensagem enviada, nunca para a recebida.
    incoming = message_row(db, external_id="IN-9")
    before = incoming.updated_at
    ignored = send_events(
        client, {"type": "receipt", "session_id": sid, "external_id": "IN-9", "status": "read"}
    )
    assert ignored == {"processed": 0, "ignored": 1}
    incoming = message_row(db, external_id="IN-9")
    assert incoming.status == "delivered"
    assert incoming.updated_at == before


def test_from_me_message_does_not_unarchive(
    client: TestClient, outbox: list, db: Session, connector: FakeConnector
) -> None:
    auth(client, outbox)
    sid = connect_ready(client, db)
    send_events(client, inbound(sid, "A1", PN, "Oi", timestamp="2030-01-10T12:00:00Z"))
    chat = client.get("/api/messaging/chats").json()[0]
    client.post(f"/api/messaging/chats/{chat['id']}/read")
    client.patch(f"/api/messaging/chats/{chat['id']}", json={"archived": True})

    # Mandei pelo celular (mais nova): atualiza a prévia, mas continua arquivada e sem não lidas.
    send_events(
        client,
        inbound(
            sid, "A2", PN, "Respondi pelo celular", from_me=True, timestamp="2030-01-10T12:05:00Z"
        ),
    )
    same = client.get(f"/api/messaging/chats/{chat['id']}").json()
    assert same["archived"] is True
    assert same["unread_count"] == 0
    assert same["last_message_preview"] == "Respondi pelo celular"


# ---------------------------------------------------------------- leitura e contatos


def test_read_self_and_contact_events(
    client: TestClient, outbox: list, db: Session, connector: FakeConnector
) -> None:
    auth(client, outbox)
    sid = connect_ready(client, db)
    send_events(client, inbound(sid, "R1", PN, "Oi"), inbound(sid, "R2", PN, "Tudo bem?"))
    chat = client.get("/api/messaging/chats").json()[0]
    assert chat["unread_count"] == 2

    # Leu no celular: zera aqui também.
    assert send_events(client, {"type": "read_self", "session_id": sid, "remote_jid": PN}) == {
        "processed": 1,
        "ignored": 0,
    }
    assert client.get(f"/api/messaging/chats/{chat['id']}").json()["unread_count"] == 0
    missing = send_events(
        client,
        {"type": "read_self", "session_id": sid, "remote_jid": "5511900000000@s.whatsapp.net"},
    )
    assert missing == {"processed": 0, "ignored": 1}

    # Nome da agenda do WhatsApp troca o número formatado.
    send_events(
        client,
        {"type": "contact", "session_id": sid, "jid": LID, "jid_alt": PN, "name": "Fernanda"},
    )
    renamed = client.get(f"/api/messaging/chats/{chat['id']}").json()
    assert renamed["name"] == "Fernanda"
    assert renamed["lid_jid"] == LID
    # Mas não troca um nome que já não é o genérico.
    again = send_events(
        client, {"type": "contact", "session_id": sid, "jid": PN, "name": "Fernanda Souza"}
    )
    assert again == {"processed": 0, "ignored": 1}
    assert client.get(f"/api/messaging/chats/{chat['id']}").json()["name"] == "Fernanda"
    # Contato sem conversa não cria conversa.
    send_events(
        client,
        {
            "type": "contact",
            "session_id": sid,
            "jid": "5511900000000@s.whatsapp.net",
            "name": "Alguém",
        },
    )
    assert len(client.get("/api/messaging/chats").json()) == 1


# ---------------------------------------------------------------- lote de eventos


def test_events_batch_is_resilient(
    client: TestClient,
    outbox: list,
    db: Session,
    connector: FakeConnector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth(client, outbox)
    sid = connect_ready(client, db)
    send_events(client, inbound(sid, "B0", PN, "Oi"))
    chat_id = message_row(db, external_id="B0").chat_id

    def broken(db_: Session, user: Any, session: Any, ev: Any) -> bool:
        # Muda algo e quebra no meio: a mudança tem que ser desfeita.
        chat = chat_rows(db_)[0]
        chat.name = "Nome que não pode ficar"
        db_.flush()
        raise RuntimeError("falha simulada")

    monkeypatch.setitem(connector_service._HANDLERS, "read_self", broken)
    result = send_events(
        client,
        {"type": "nao-existe", "session_id": sid},
        {"type": "message", "session_id": sid},
        inbound(str(uuid.uuid4()), "B1", PN, "Sessão desconhecida"),
        {"type": "read_self", "session_id": sid, "remote_jid": PN},
        inbound(sid, "B2", PN, "Esta entra"),
    )
    assert result == {"processed": 1, "ignored": 4}
    names = [c.name for c in chat_rows(db)]
    assert names == ["+55 (11) 97777-6666"]
    assert message_row(db, external_id="B2").chat_id == chat_id

    too_many = client.post(
        "/api/messaging/connector/events",
        json={"events": [{"type": "status"}] * 501},
        headers=connector_headers(),
    )
    assert too_many.status_code == 422

    # Conta bloqueada: eventos ignorados.
    _block(db, "ana@example.com")
    assert send_events(client, inbound(sid, "B3", PN, "Bloqueada")) == {
        "processed": 0,
        "ignored": 1,
    }


# ---------------------------------------------------------------- migração 0035


def _load_migration(name: str):  # type: ignore[no-untyped-def]
    path = Path(__file__).parents[1] / "alembic" / "versions" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_0035_converts_old_data(tmp_path: Path) -> None:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    m34 = _load_migration("20261119_0034_v1101_mensageria.py")
    m35 = _load_migration("20261119_0035_v1101_mensageria_conector.py")
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'migracao.db'}")
    user_id = uuid.uuid4().hex
    session_id = uuid.uuid4().hex
    pn_chat, lid_chat = uuid.uuid4().hex, uuid.uuid4().hex
    created = "2026-11-19 10:00:00.000000"

    def run(module, step: str) -> None:  # type: ignore[no-untyped-def]
        with engine.begin() as conn:
            module.op = Operations(MigrationContext.configure(conn))
            getattr(module, step)()

    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE users (id CHAR(32) PRIMARY KEY)")
        conn.exec_driver_sql(f"INSERT INTO users VALUES ('{user_id}')")
    run(m34, "upgrade")
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO messaging_sessions (id, user_id, status, bridge_token_hash, "
            f"created_at, updated_at) VALUES ('{session_id}', '{user_id}', 'authenticated', "
            f"'abc', '{created}', '{created}')"
        )
        for chat_id, jid, phone in (
            (pn_chat, "5511977776666@c.us", "5511977776666"),
            (lid_chat, "123456789012345@lid", "123456789012345"),
        ):
            conn.exec_driver_sql(
                "INSERT INTO messaging_chats (id, user_id, remote_jid, phone, name, unread_count, "
                f"pinned, archived, created_at, updated_at) VALUES ('{chat_id}', '{user_id}', "
                f"'{jid}', '{phone}', 'Contato', 0, 0, 0, '{created}', '{created}')"
            )
        conn.exec_driver_sql(
            "INSERT INTO messaging_messages (id, user_id, chat_id, direction, body, message_type, "
            f"status, external_id, created_at) VALUES ('{uuid.uuid4().hex}', '{user_id}', "
            f"'{pn_chat}', 'in', 'Oi', 'chat', 'delivered', 'X1', '{created}')"
        )

    run(m35, "upgrade")
    with engine.begin() as conn:
        session = conn.execute(sa.text("SELECT * FROM messaging_sessions")).mappings().one()
        assert session["status"] == "connecting"
        assert session["wanted"] == 0
        assert "bridge_token_hash" not in session
        chats = {
            row["id"]: row
            for row in conn.execute(sa.text("SELECT * FROM messaging_chats")).mappings()
        }
        assert chats[pn_chat]["remote_jid"] == "5511977776666@s.whatsapp.net"
        assert chats[pn_chat]["phone"] == "5511977776666"
        assert chats[lid_chat]["lid_jid"] == "123456789012345@lid"
        assert chats[lid_chat]["phone"] is None
        message = conn.execute(sa.text("SELECT * FROM messaging_messages")).mappings().one()
        assert message["updated_at"] == created
        assert message["claimed_at"] is None
        # Deduplicação garantida pelo banco.
        with pytest.raises(sa.exc.IntegrityError), conn.begin_nested():
            conn.exec_driver_sql(
                "INSERT INTO messaging_messages (id, user_id, chat_id, direction, body, "
                "message_type, status, external_id, created_at, updated_at) VALUES "
                f"('{uuid.uuid4().hex}', '{user_id}', '{pn_chat}', 'in', 'Oi', 'chat', "
                f"'delivered', 'X1', '{created}', '{created}')"
            )
        conn.exec_driver_sql(
            "INSERT INTO messaging_auth_keys (session_id, category, key_id, value) VALUES "
            f"('{session_id}', 'creds', '', '{{}}')"
        )
        conn.exec_driver_sql(
            "INSERT INTO messaging_connector_kv (key, value) VALUES ('wa_version', '[2,3000,1]')"
        )
        stored = conn.execute(sa.text("SELECT updated_at FROM messaging_connector_kv")).scalar()
        assert stored is not None

    run(m35, "downgrade")
    with engine.begin() as conn:
        session = conn.execute(sa.text("SELECT * FROM messaging_sessions")).mappings().one()
        assert session["status"] == "authenticated"
        assert "wanted" not in session
        chats = {
            row["id"]: row
            for row in conn.execute(sa.text("SELECT * FROM messaging_chats")).mappings()
        }
        assert chats[pn_chat]["remote_jid"] == "5511977776666@c.us"
        assert chats[lid_chat]["phone"] == "123456789012345"
        tables = set(sa.inspect(conn).get_table_names())
        assert "messaging_auth_keys" not in tables
        assert "messaging_connector_kv" not in tables
    engine.dispose()
