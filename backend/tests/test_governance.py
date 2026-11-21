"""Testes de governança, permissões granulares no /admin, proteção de dados sensíveis e cotas."""

import io

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import User
from tests.conftest import create_verified_user, login


def _make_admin(
    client: TestClient, db: Session, outbox: list, email: str = "adm@example.com"
) -> User:
    create_verified_user(client, outbox, email)
    user = db.scalar(select(User).where(User.email == email))
    assert user is not None
    user.is_admin = True
    db.commit()
    db.refresh(user)
    return user


def _make_user(
    client: TestClient, db: Session, outbox: list, email: str = "comum@example.com"
) -> User:
    create_verified_user(client, outbox, email)
    user = db.scalar(select(User).where(User.email == email))
    assert user is not None
    db.commit()
    db.refresh(user)
    return user


def _png_bytes(size: int = 32) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (size, size), color=(30, 120, 90)).save(buf, format="PNG")
    return buf.getvalue()


def test_common_user_cannot_access_admin_or_sensitive_system_routes(
    client: TestClient, db: Session, outbox: list
) -> None:
    _make_user(client, db, outbox, "comum@example.com")
    assert login(client, "comum@example.com").status_code == 200

    # Rotas do painel admin bloqueadas para usuário comum (403 Forbidden).
    assert client.get("/api/admin/overview").status_code == 403
    assert client.get("/api/admin/users").status_code == 403
    assert client.get("/api/admin/emails").status_code == 403
    assert client.get("/api/admin/governance").status_code == 403
    assert (
        client.put("/api/admin/governance", json={"global_blocked_resources": ["crm"]}).status_code
        == 403
    )
    assert client.get("/api/admin/errors").status_code == 403

    # Conector WhatsApp exige X-Connector-Token interno (usuário comum não acessa).
    assert client.get("/api/messaging/connector/sessions").status_code in (401, 403, 503)


def test_admin_can_block_solution_and_subfeatures_per_user_and_globally(
    client: TestClient, db: Session, outbox: list, monkeypatch
) -> None:
    monkeypatch.setattr(get_settings(), "messaging_connector_token", "tok-local")
    monkeypatch.setattr(get_settings(), "messaging_connector_url", "http://conector.test")

    adm = _make_admin(client, db, outbox, "chefe@example.com")
    comum = _make_user(client, db, outbox, "cliente@example.com")

    # Entra como admin e bloqueia Mensageria + API externa apenas para cliente@example.com.
    assert login(client, adm.email).status_code == 200
    gov = client.get("/api/admin/governance")
    assert gov.status_code == 200
    assert any(s["id"] == "mensageria" for s in gov.json()["solutions"])
    assert any(f["id"] == "feature:external_api" for f in gov.json()["features"])

    patch_res = client.patch(
        f"/api/admin/users/{comum.id}/permissions",
        json={
            "blocked_resources": ["mensageria", "feature:external_api", "feature:data_export"],
            "storage_quota_mb": 10,
        },
    )
    assert patch_res.status_code == 200, patch_res.text
    assert patch_res.json()["storage_quota_mb"] == 10
    assert "mensageria" in patch_res.json()["blocked_resources"]

    # Admin não pode bloquear recursos na própria conta nem é afetado pelo bloqueio global.
    self_block = client.patch(
        f"/api/admin/users/{adm.id}/permissions",
        json={"blocked_resources": ["mensageria"]},
    )
    assert self_block.status_code == 400

    # Loga como o usuário comum e confere que /auth/me reflete e as APIs respondem 403.
    client.post("/api/auth/logout")
    assert login(client, comum.email).status_code == 200
    me = client.get("/api/auth/me").json()
    assert "mensageria" in me["blocked_resources"]
    assert me["storage_quota_mb"] == 10

    # Mensageria bloqueada (403); CRM livre, API externa e Exportação bloqueadas (403).
    msg_res = client.get("/api/messaging/chats")
    assert msg_res.status_code == 403
    assert msg_res.json()["error"] == "resource_blocked"

    assert client.get("/api/crm/dashboards").status_code == 200
    api_res = client.post(
        "/api/crm/sources/preview/api",
        json={"url": "https://example.com/data.json"},
    )
    assert api_res.status_code == 403
    assert api_res.json()["error"] == "resource_blocked"

    assert client.get("/api/categories").status_code == 200
    exp_res = client.get("/api/export/backup")
    assert exp_res.status_code == 403

    # Bloqueio global: admin bloqueia "dashboard-crm" para todos os usuários comuns.
    client.post("/api/auth/logout")
    assert login(client, adm.email).status_code == 200
    put_gov = client.put(
        "/api/admin/governance",
        json={"global_blocked_resources": ["dashboard-crm"]},
    )
    assert put_gov.status_code == 200
    assert put_gov.json()["global_blocked_resources"] == ["dashboard-crm"]

    # Admin continua acessando normalmente.
    assert client.get("/api/crm/dashboards").status_code == 200

    # Usuário comum fica bloqueado no CRM também.
    client.post("/api/auth/logout")
    assert login(client, comum.email).status_code == 200
    assert client.get("/api/crm/dashboards").status_code == 403


def test_storage_quota_blocks_uploads_above_user_limit(
    client: TestClient, db: Session, outbox: list
) -> None:
    adm = _make_admin(client, db, outbox, "admin_cota@example.com")
    comum = _make_user(client, db, outbox, "usuario_cota@example.com")

    assert login(client, adm.email).status_code == 200
    assert (
        client.patch(
            f"/api/admin/users/{comum.id}/permissions",
            json={"blocked_resources": [], "storage_quota_mb": 5},
        ).status_code
        == 200
    )

    # Simula uso prévio de 5 MB menos 10 bytes.
    from app.models import StoredFile

    db.add(
        StoredFile(
            owner_id=comum.id,
            purpose="attachment",
            filename="grande.bin",
            content_type="application/octet-stream",
            size=5 * 1024 * 1024 - 10,
            width=0,
            height=0,
            data=b"x",
        )
    )
    db.commit()

    client.post("/api/auth/logout")
    assert login(client, comum.email).status_code == 200

    # Arquivo permanente (Cofre) passa da cota: bloqueado.
    up = client.post(
        "/api/cofre/documents",
        files={"file": ("foto.png", _png_bytes(64), "image/png")},
        data={"title": "Documento"},
    )
    assert up.status_code == 413
    assert up.json()["error"] == "quota_exceeded"

    # Mídia da Mensageria não conta na cota de arquivos (D4, 21/11/2026): a recusa aqui é só
    # por falta de WhatsApp conectado, nunca por cota.
    chat = client.post(
        "/api/messaging/chats", json={"phone": "5511977776666", "name": "Teste"}
    ).json()
    media = client.post(
        f"/api/messaging/chats/{chat['id']}/media",
        files={"file": ("foto.png", _png_bytes(64), "image/png")},
    )
    assert media.json()["error"] != "quota_exceeded"


def test_calendar_feed_respects_blocked_meu_orcamento(
    client: TestClient, db: Session, outbox: list
) -> None:
    adm = _make_admin(client, db, outbox, "admin_ics@example.com")
    comum = _make_user(client, db, outbox, "user_ics@example.com")

    assert login(client, comum.email).status_code == 200
    link_res = client.post("/api/calendar-link")
    assert link_res.status_code == 200
    feed_url = link_res.json()["url"]
    assert feed_url is not None
    feed_path = "/api/" + feed_url.split("/api/", 1)[1]

    # Sem sessão, com meu-orcamento liberado: devolve 200 text/calendar.
    client.post("/api/auth/logout")
    ok_res = client.get(feed_path)
    assert ok_res.status_code == 200
    assert "BEGIN:VCALENDAR" in ok_res.text

    # Admin bloqueia meu-orcamento para comum: feed retorna 404 sem revelar o link.
    assert login(client, adm.email).status_code == 200
    assert (
        client.patch(
            f"/api/admin/users/{comum.id}/permissions",
            json={"blocked_resources": ["meu-orcamento"], "storage_quota_mb": 50},
        ).status_code
        == 200
    )
    client.post("/api/auth/logout")
    blocked_res = client.get(feed_path)
    assert blocked_res.status_code == 404
