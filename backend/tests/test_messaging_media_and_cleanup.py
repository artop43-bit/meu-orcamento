"""Testes de mídias, fotos de perfil, prioridade de nomes e limpeza semanal da Mensageria."""

import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cli import cleanup as run_cli_cleanup
from app.db.types import utcnow
from app.models import MessagingChat, MessagingMedia, MessagingMessage
from app.services.messaging import MAX_MEDIA_BYTES, purge_old
from tests.messaging_helpers import (
    FakeConnector,
    auth,
    claim,
    connect_ready,
    connector_headers,
    inbound,
    install_fake_connector,
    message_row,
    send_events,
)

PN = "5511977776666@s.whatsapp.net"
LID = "123456789012345@lid"
TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc`\x00\x00"
    b"\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture
def connector(monkeypatch: pytest.MonkeyPatch) -> FakeConnector:
    return install_fake_connector(monkeypatch)


def test_contact_name_priority_and_masked_phone_rejection(
    client: TestClient, outbox: list, db: Session, connector: FakeConnector
) -> None:
    auth(client, outbox)
    sid = connect_ready(client, db)

    # Mensagem chega com número mascarado como push_name: não trava o nome.
    send_events(client, inbound(sid, "M1", LID, "Oi", push_name="+55·······80"))
    chat = client.get("/api/messaging/chats").json()[0]
    assert chat["name"] == "Contato do WhatsApp"

    # Apelido só com pontuação também é ignorado.
    send_events(client, inbound(sid, "M2", LID, "Tudo bem?", push_name="."))
    assert client.get(f"/api/messaging/chats/{chat['id']}").json()["name"] == "Contato do WhatsApp"

    # Apelido real (push) substitui o genérico.
    send_events(client, inbound(sid, "M3", LID, "Sou a Luana", push_name="luana"))
    assert client.get(f"/api/messaging/chats/{chat['id']}").json()["name"] == "luana"

    # Nome da agenda do celular (source="contact") tem prioridade sobre o apelido (push).
    res = send_events(
        client,
        {
            "type": "contact",
            "session_id": sid,
            "jid": LID,
            "jid_alt": PN,
            "name": "Luana Silva",
            "source": "contact",
        },
    )
    assert res == {"processed": 1, "ignored": 0}
    updated = client.get(f"/api/messaging/chats/{chat['id']}").json()
    assert updated["name"] == "Luana Silva"
    assert updated["remote_jid"] == PN
    assert updated["lid_jid"] == LID

    # Apelido novo depois da agenda não substitui a agenda.
    send_events(client, inbound(sid, "M4", PN, "Beleza", push_name="lu"))
    assert client.get(f"/api/messaging/chats/{chat['id']}").json()["name"] == "Luana Silva"

    # Nome editado no Hub (manual) nunca é sobrescrito nem pela agenda.
    client.patch(f"/api/messaging/chats/{chat['id']}", json={"name": "Luana (Cliente)"})
    send_events(
        client,
        {
            "type": "contact",
            "session_id": sid,
            "jid": PN,
            "name": "Outro Nome",
            "source": "contact",
        },
    )
    assert client.get(f"/api/messaging/chats/{chat['id']}").json()["name"] == "Luana (Cliente)"


def test_contact_event_without_name_merges_duplicate_lid_and_pn(
    client: TestClient, outbox: list, db: Session, connector: FakeConnector
) -> None:
    auth(client, outbox)
    sid = connect_ready(client, db)
    send_events(
        client,
        inbound(sid, "D1", LID, "Oi pelo LID", push_name="luana"),
        inbound(sid, "D2", PN, "Oi pelo número", push_name="Luana"),
    )
    assert len(client.get("/api/messaging/chats").json()) == 2

    # Evento de mapeamento sem nome une as duas conversas numa só.
    merged = send_events(
        client,
        {"type": "contact", "session_id": sid, "jid": LID, "jid_alt": PN, "name": None},
    )
    assert merged == {"processed": 1, "ignored": 0}
    chats = client.get("/api/messaging/chats").json()
    assert len(chats) == 1
    assert chats[0]["remote_jid"] == PN
    assert chats[0]["lid_jid"] == LID
    page = client.get(f"/api/messaging/chats/{chats[0]['id']}/messages").json()
    assert sorted(m["external_id"] for m in page["items"]) == ["D1", "D2"]


def test_history_message_preserves_delivery_and_read_status(
    client: TestClient, outbox: list, db: Session, connector: FakeConnector
) -> None:
    auth(client, outbox)
    sid = connect_ready(client, db)
    send_events(
        client,
        inbound(sid, "H1", PN, "Enviada", from_me=True, history=True, status="delivered"),
        inbound(sid, "H2", PN, "Lida", from_me=True, history=True, status="played"),
    )
    assert message_row(db, external_id="H1").status == "delivered"
    assert message_row(db, external_id="H2").status == "read"


def test_receive_attach_and_send_media_and_avatar(
    client: TestClient, outbox: list, db: Session, connector: FakeConnector
) -> None:
    auth(client, outbox, "ana@example.com")
    sid = connect_ready(client, db, "ana@example.com")

    # 1. Conector envia mensagem de foto, depois sobe o binário e liga com media_attach.
    send_events(client, inbound(sid, "IMG-1", PN, "📷 Foto · recibo", message_type="image"))
    chat = client.get("/api/messaging/chats").json()[0]

    up = client.post(
        f"/api/messaging/connector/sessions/{sid}/media",
        params={"kind": "image", "mime_type": "image/png", "file_name": "recibo.png"},
        content=TINY_PNG,
        headers=connector_headers(),
    )
    assert up.status_code == 200, up.text
    media_id = up.json()["media_id"]

    att = send_events(
        client,
        {"type": "media_attach", "session_id": sid, "external_id": "IMG-1", "media_id": media_id},
    )
    assert att == {"processed": 1, "ignored": 0}

    page = client.get(f"/api/messaging/chats/{chat['id']}/messages").json()
    msg = page["items"][0]
    assert msg["media_id"] == media_id
    assert msg["media_mime"] == "image/png"
    assert msg["media_url"] == f"/api/messaging/media/{media_id}"

    dl = client.get(msg["media_url"])
    assert dl.status_code == 200
    assert dl.content == TINY_PNG
    assert dl.headers["content-type"].startswith("image/png")
    assert "inline" in dl.headers["content-disposition"]

    # 2. Foto de perfil do contato via conector.
    av_up = client.post(
        f"/api/messaging/connector/sessions/{sid}/avatar",
        params={"jid": PN, "mime_type": "image/png"},
        content=TINY_PNG,
        headers=connector_headers(),
    )
    assert av_up.status_code == 200
    assert av_up.json() == {"saved": True}

    chat_after = client.get(f"/api/messaging/chats/{chat['id']}").json()
    assert chat_after["avatar_url"] is not None
    av_get = client.get(chat_after["avatar_url"])
    assert av_get.status_code == 200
    assert av_get.content == TINY_PNG

    # 3. Envio de mídia pela tela (com legenda) entra na fila do conector.
    sent = client.post(
        f"/api/messaging/chats/{chat['id']}/media",
        files={"file": ("nota.png", TINY_PNG, "image/png")},
        data={"caption": "Segue o comprovante"},
    )
    assert sent.status_code == 201, sent.text
    sent_json = sent.json()
    assert sent_json["message_type"] == "image"
    assert sent_json["body"] == "📷 Foto · Segue o comprovante"
    assert sent_json["media_id"] is not None

    items = claim(client, sid)
    assert len(items) == 1
    assert items[0]["message_type"] == "image"
    assert items[0]["caption"] == "Segue o comprovante"
    assert items[0]["media"]["media_id"] == sent_json["media_id"]

    fetched = client.get(
        f"/api/messaging/connector/sessions/{sid}/media/{sent_json['media_id']}",
        headers=connector_headers(),
    )
    assert fetched.status_code == 200
    assert fetched.content == TINY_PNG

    # 4. SVG nunca é servido inline (vira documento com attachment).
    svg = client.post(
        f"/api/messaging/chats/{chat['id']}/media",
        files={"file": ("icone.svg", b"<svg></svg>", "image/svg+xml")},
    )
    assert svg.status_code == 201
    assert svg.json()["message_type"] == "document"
    svg_dl = client.get(svg.json()["media_url"])
    assert "attachment" in svg_dl.headers["content-disposition"]

    # 5. Arquivo acima de 8 MB é recusado.
    huge = client.post(
        f"/api/messaging/chats/{chat['id']}/media",
        files={"file": ("grande.bin", b"0" * (MAX_MEDIA_BYTES + 1), "application/octet-stream")},
    )
    assert huge.status_code == 413

    # 6. Isolamento entre usuários: outro usuário não baixa mídia nem avatar da Ana.
    client.post("/api/auth/logout")
    auth(client, outbox, "bruno@example.com")
    assert client.get(msg["media_url"]).status_code == 404
    assert client.get(chat_after["avatar_url"]).status_code == 404


def test_weekly_cleanup_removes_old_messages_media_and_unpinned_chats(
    client: TestClient, outbox: list, db: Session, connector: FakeConnector
) -> None:
    auth(client, outbox)
    sid = connect_ready(client, db)
    old_ts = (utcnow() - timedelta(days=9)).isoformat()
    recent_ts = (utcnow() - timedelta(days=1)).isoformat()

    pn_old = "5511911110001@s.whatsapp.net"
    pn_pinned = "5511911110002@s.whatsapp.net"
    pn_mixed = "5511911110003@s.whatsapp.net"

    send_events(
        client,
        inbound(sid, "OLD-1", pn_old, "Mensagem velha", timestamp=old_ts),
        inbound(sid, "PIN-1", pn_pinned, "Velha mas fixada", timestamp=old_ts),
        inbound(sid, "MIX-OLD", pn_mixed, "Antiga da mista", timestamp=old_ts),
        inbound(sid, "MIX-NEW", pn_mixed, "Nova da mista", timestamp=recent_ts),
    )
    chats = {c["remote_jid"]: c for c in client.get("/api/messaging/chats").json()}
    client.patch(f"/api/messaging/chats/{chats[pn_pinned]['id']}", json={"pinned": True})

    # Anexa uma mídia à mensagem antiga e envelhece sua data também.
    up = client.post(
        f"/api/messaging/connector/sessions/{sid}/media",
        params={"kind": "image", "mime_type": "image/png", "file_name": "antiga.png"},
        content=TINY_PNG,
        headers=connector_headers(),
    )
    old_media_id = uuid.UUID(up.json()["media_id"])
    send_events(
        client,
        {
            "type": "media_attach",
            "session_id": sid,
            "external_id": "OLD-1",
            "media_id": str(old_media_id),
        },
    )
    db.expire_all()
    media_obj = db.get(MessagingMedia, old_media_id)
    assert media_obj is not None
    media_obj.created_at = utcnow() - timedelta(days=9)
    db.commit()

    removed = purge_old(db)
    db.commit()
    assert removed == {"messages": 3, "media": 1, "chats": 1}

    db.expire_all()
    remaining_jids = {c.remote_jid for c in db.scalars(select(MessagingChat)).all()}
    # Conversa antiga não fixada saiu; fixada e mista continuaram.
    assert remaining_jids == {pn_pinned, pn_mixed}
    remaining_msgs = [m.external_id for m in db.scalars(select(MessagingMessage)).all()]
    assert remaining_msgs == ["MIX-NEW"]
    assert db.get(MessagingMedia, old_media_id) is None

    # Também roda dentro do `cleanup` do agendador (cli.py).
    cli_res = run_cli_cleanup(db)
    assert "messaging_messages" in cli_res
    assert "messaging_media" in cli_res
    assert "messaging_chats" in cli_res


def test_audio_media_range_streaming_and_magic_byte_mime_sniffing(
    client: TestClient, outbox: list, db: Session, connector: FakeConnector
) -> None:
    auth(client, outbox)
    sid = connect_ready(client, db)
    fake_ogg = b"OggS\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00OpusHead" + b"\x01" * 40

    send_events(client, inbound(sid, "AUD-1", PN, "🎤 Áudio", message_type="audio"))
    chat = client.get("/api/messaging/chats").json()[0]

    # Sobe com mime genérico application/octet-stream (comum em histórico antigo do WhatsApp).
    up = client.post(
        f"/api/messaging/connector/sessions/{sid}/media",
        params={"kind": "audio", "mime_type": "application/octet-stream", "file_name": "voz.ogg"},
        content=fake_ogg,
        headers=connector_headers(),
    )
    assert up.status_code == 200
    media_id = up.json()["media_id"]
    send_events(
        client,
        {"type": "media_attach", "session_id": sid, "external_id": "AUD-1", "media_id": media_id},
    )

    page = client.get(f"/api/messaging/chats/{chat['id']}/messages").json()
    media_url = page["items"][0]["media_url"]
    assert media_url == f"/api/messaging/media/{media_id}"

    # Resposta completa detecta audio/ogg pelos magic bytes e informa Accept-Ranges: bytes.
    full = client.get(media_url)
    assert full.status_code == 200
    assert full.headers["content-type"].startswith("audio/ogg")
    assert full.headers["accept-ranges"] == "bytes"
    assert full.content == fake_ogg

    # Requisição parcial HTTP Range (necessária para seek e duração no player de áudio).
    partial = client.get(media_url, headers={"Range": "bytes=0-3"})
    assert partial.status_code == 206
    assert partial.content == b"OggS"
    assert partial.headers["content-range"] == f"bytes 0-3/{len(fake_ogg)}"
    assert partial.headers["content-length"] == "4"

    # Range inválido responde 416.
    invalid = client.get(media_url, headers={"Range": "bytes=9999-10000"})
    assert invalid.status_code == 416


def test_messaging_crm_360_tags_followup_quick_replies_and_budget_entry(
    client: TestClient, outbox: list, db: Session, connector: FakeConnector
) -> None:
    auth(client, outbox)
    sid = connect_ready(client, db)
    send_events(
        client,
        inbound(sid, "CRM-1", PN, "Oi, paguei R$ 240,00 no Pix", push_name="Marina Costa"),
    )
    chat = client.get("/api/messaging/chats").json()[0]
    chat_id = chat["id"]

    # 1. Etiquetas, status de atendimento e follow-up agendado.
    followup_iso = (utcnow() + timedelta(hours=3)).isoformat()
    patched = client.patch(
        f"/api/messaging/chats/{chat_id}",
        json={
            "tags": ["VIP", "Orçamento", "vip"],
            "service_status": "waiting",
            "followup_at": followup_iso,
            "followup_note": "Confirmar proposta comercial",
        },
    )
    assert patched.status_code == 200, patched.text
    p_data = patched.json()
    assert p_data["tags"] == ["VIP", "Orçamento"]
    assert p_data["service_status"] == "waiting"
    assert p_data["followup_note"] == "Confirmar proposta comercial"
    assert p_data["followup_at"] is not None

    # Filtros por follow-up, status e etiqueta.
    assert len(client.get("/api/messaging/chats", params={"filter": "followup"}).json()) == 1
    assert len(client.get("/api/messaging/chats", params={"filter": "waiting"}).json()) == 1
    assert len(client.get("/api/messaging/chats", params={"filter": "resolved"}).json()) == 0
    assert len(client.get("/api/messaging/chats", params={"tag": "vip"}).json()) == 1
    assert len(client.get("/api/messaging/chats", params={"tag": "Inexistente"}).json()) == 0

    # 2. Respostas rápidas com / (semeadas automaticamente + CRUD).
    qrs = client.get("/api/messaging/quick-replies")
    assert qrs.status_code == 200
    shortcuts = [r["shortcut"] for r in qrs.json()]
    assert "/pix" in shortcuts
    assert "/cobranca" in shortcuts

    created_qr = client.post(
        "/api/messaging/quick-replies",
        json={
            "shortcut": "agenda",
            "title": "Link da agenda",
            "body": "Oi {nome}, escolha seu horário!",
            "category": "Comercial",
        },
    )
    assert created_qr.status_code == 201
    assert created_qr.json()["shortcut"] == "/agenda"
    del_qr = client.delete(f"/api/messaging/quick-replies/{created_qr.json()['id']}")
    assert del_qr.status_code == 204

    # 3. Criar negócio no Funil CRM direto da conversa e consultar contexto 360°.
    deal_res = client.post(
        f"/api/messaging/chats/{chat_id}/crm-deal",
        json={"title": "Consultoria Marina", "amount": "1500.00"},
    )
    assert deal_res.status_code == 201, deal_res.text
    assert deal_res.json()["deal"]["title"] == "Consultoria Marina"

    crm_ctx = client.get(f"/api/messaging/chats/{chat_id}/crm-context")
    assert crm_ctx.status_code == 200
    ctx_data = crm_ctx.json()
    assert ctx_data["contact"] is not None
    assert ctx_data["contact"]["name"] == "Marina Costa"
    assert len(ctx_data["deals"]) == 1
    assert len(ctx_data["stages"]) >= 3

    # 4. Lançar Receita e Despesa no Meu Orçamento direto da conversa.
    inc_res = client.post(
        f"/api/messaging/chats/{chat_id}/budget-entry",
        json={
            "kind": "income",
            "description": "Consultoria Marina via WhatsApp",
            "amount": "240.00",
        },
    )
    assert inc_res.status_code == 201, inc_res.text
    assert inc_res.json()["kind"] == "income"

    exp_res = client.post(
        f"/api/messaging/chats/{chat_id}/budget-entry",
        json={
            "kind": "expense",
            "description": "Taxa de entrega Marina",
            "amount": "35.50",
            "payment_method": "pix",
        },
    )
    assert exp_res.status_code == 201, exp_res.text
    assert exp_res.json()["kind"] == "expense"

    b_ctx = client.get("/api/messaging/budget-context", params={"chat_id": chat_id})
    assert b_ctx.status_code == 200
    assert Decimal_str(b_ctx.json()["income_total"]) == "240.00"
    assert len(b_ctx.json()["categories"]) > 0


def Decimal_str(val: object) -> str:
    return f"{float(str(val)):.2f}"


@pytest.mark.parametrize(
    ("brand", "mime", "kind"),
    [
        (b"heic", "image/heic", "image"),
        (b"heix", "image/heic", "image"),
        (b"hevc", "image/heic", "image"),
        (b"heim", "image/heic", "image"),
        (b"heis", "image/heic", "image"),
        (b"mif1", "image/heic", "image"),
        (b"msf1", "image/heic", "image"),
        (b"avif", "image/avif", "image"),
        (b"avis", "image/avif", "image"),
        (b"M4A ", "audio/mp4", "audio"),
    ],
)
def test_iso_media_brands_are_not_misidentified_as_video(
    brand: bytes, mime: str, kind: str
) -> None:
    from app.services.messaging.media import infer_media_kind, sniff_media_mime

    raw = b"\x00\x00\x00\x18ftyp" + brand + b"\x00\x00\x00\x00"
    actual = sniff_media_mime(raw, "application/octet-stream")
    assert actual == mime
    assert infer_media_kind(actual) == kind


def test_heic_and_avif_uploads_are_photos_even_with_generic_metadata(
    client: TestClient, outbox: list, db: Session, connector: FakeConnector
) -> None:
    auth(client, outbox)
    sid = connect_ready(client, db)
    for brand, mime in ((b"heic", "image/heic"), (b"avif", "image/avif")):
        res = client.post(
            f"/api/messaging/connector/sessions/{sid}/media",
            params={"kind": "video", "mime_type": "application/octet-stream"},
            content=b"\x00\x00\x00\x18ftyp" + brand + b"\x00\x00\x00\x00",
            headers=connector_headers(),
        )
        assert res.status_code == 200, res.text
        assert res.json()["kind"] == "image"
        assert res.json()["mime_type"] == mime


@pytest.mark.parametrize(
    "protected", ["tags", "notes", "budget_person", "followup_at", "followup_note", "crm"]
)
def test_cleanup_preserves_important_contact_but_expires_messages(
    client: TestClient, outbox: list, db: Session, connector: FakeConnector, protected: str
) -> None:
    from app.models import CrmContact

    auth(client, outbox)
    sid = connect_ready(client, db)
    old = utcnow() - timedelta(days=9)
    send_events(
        client, inbound(sid, "EXPIRE", PN, "Mensagem antiga", timestamp=int(old.timestamp()))
    )
    chat = db.scalar(select(MessagingChat))
    assert chat is not None
    if protected == "crm":
        db.add(CrmContact(user_id=chat.user_id, name="Cliente CRM", messaging_chat_id=chat.id))
    elif protected == "followup_at":
        chat.followup_at = utcnow() + timedelta(days=2)
    else:
        setattr(chat, protected, "Cliente importante")
    db.commit()
    result = purge_old(db)
    db.commit()
    db.expire_all()
    assert result["messages"] == 1
    assert result["chats"] == 0
    assert db.get(MessagingChat, chat.id) is not None


def test_merge_preserves_crm_tags_status_and_earliest_followup(
    client: TestClient, outbox: list, db: Session, connector: FakeConnector
) -> None:
    from app.models import CrmContact

    auth(client, outbox)
    sid = connect_ready(client, db)
    send_events(client, inbound(sid, "LID-META", LID, "LID"), inbound(sid, "PN-META", PN, "PN"))
    primary = db.scalar(select(MessagingChat).where(MessagingChat.remote_jid == PN))
    other = db.scalar(select(MessagingChat).where(MessagingChat.remote_jid == LID))
    assert primary is not None and other is not None
    primary.tags = "Lead,VIP"
    other.tags = "VIP,Cliente"
    other.service_status = "waiting"
    other.followup_at = utcnow() + timedelta(days=1)
    other.followup_note = "Enviar proposta"
    other.budget_person = "Cliente"
    expected_followup = other.followup_at
    contact = CrmContact(user_id=primary.user_id, name="Cliente", messaging_chat_id=other.id)
    db.add(contact)
    db.commit()
    primary_id = primary.id
    other_id = other.id
    contact_id = contact.id
    send_events(client, {"type": "contact", "session_id": sid, "jid": LID, "jid_alt": PN})
    db.expire_all()
    merged = db.get(MessagingChat, primary_id)
    assert merged is not None
    assert db.get(MessagingChat, other_id) is None
    assert set(merged.tags.split(",")) == {"Lead", "VIP", "Cliente"}
    assert merged.service_status == "waiting"
    assert merged.followup_at == expected_followup
    assert merged.followup_note == "Enviar proposta"
    assert merged.budget_person == "Cliente"
    assert db.get(CrmContact, contact_id).messaging_chat_id == primary_id


def test_polling_chats_and_media_metadata_does_not_load_binary_payloads(
    client: TestClient, outbox: list, db: Session
) -> None:
    from sqlalchemy import inspect

    from app.services.messaging.chats import chat_avatar_url

    auth(client, outbox)
    created = client.post("/api/messaging/chats", json={"phone": "5511966665555"}).json()
    chat = db.get(MessagingChat, uuid.UUID(created["id"]))
    chat.avatar_data = TINY_PNG
    chat.avatar_mime = "image/png"
    media = MessagingMedia(
        user_id=chat.user_id,
        kind="image",
        mime_type="image/png",
        size_bytes=len(TINY_PNG),
        data=TINY_PNG,
    )
    db.add(media)
    db.commit()
    chat_id, media_id = chat.id, media.id
    db.expunge_all()
    loaded_chat = db.scalar(select(MessagingChat).where(MessagingChat.id == chat_id))
    loaded_media = db.scalar(select(MessagingMedia).where(MessagingMedia.id == media_id))
    assert "avatar_data" in inspect(loaded_chat).unloaded
    assert "data" in inspect(loaded_media).unloaded
    assert chat_avatar_url(loaded_chat) is not None
    assert "avatar_data" in inspect(loaded_chat).unloaded
    assert client.get(f"/api/messaging/chats/{chat_id}/avatar").content == TINY_PNG
