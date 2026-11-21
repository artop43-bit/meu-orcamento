"""Testes da Fase D: Cofre de Documentos (`/cofre`), Caderno (`/caderno`) e pontes 360°."""

from __future__ import annotations

import io
import uuid
from datetime import date, timedelta

import pymupdf
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Expense, MessagingChat, MessagingMedia, MessagingMessage, Project, User
from app.services.budget import ensure_month
from app.services.messaging.cleanup import purge_old
from tests.conftest import create_verified_user, login


def _make_user(
    client: TestClient, db: Session, outbox: list, email: str, *, is_admin: bool = False
) -> User:
    create_verified_user(client, outbox, email)
    user = db.scalar(select(User).where(User.email == email))
    assert user is not None
    if is_admin:
        user.is_admin = True
    db.commit()
    db.refresh(user)
    return user


def _pdf_bytes(text: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=12)
    out = doc.tobytes()
    doc.close()
    return out


def _png_bytes(size: int = 32) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (size, size), color=(25, 130, 95)).save(buf, format="PNG")
    return buf.getvalue()


def test_vault_upload_search_expiry_agenda_bridges_and_security(
    client: TestClient, db: Session, outbox: list
) -> None:
    adm = _make_user(client, db, outbox, "admin_fase_d@example.com", is_admin=True)
    user_a = _make_user(client, db, outbox, "cofre_a@example.com")
    user_b = _make_user(client, db, outbox, "cofre_b@example.com")

    assert login(client, user_a.email).status_code == 200

    # 1) Upload de PDF com extração digital de texto e validade próxima (10 dias).
    exp_date = (date.today() + timedelta(days=10)).isoformat()
    pdf = _pdf_bytes("Certificado de Garantia Geladeira FrostFree Modelo XYZ-9000 Nota 4412")
    up = client.post(
        "/api/cofre/documents",
        files={"file": ("garantia-geladeira.pdf", pdf, "application/pdf")},
        data={
            "title": "Garantia Geladeira Cozinha",
            "category": "warranty",
            "issuer": "Eletro Sul",
            "document_number": "NF-4412",
            "expires_at": exp_date,
            "notify_days_before": "30",
        },
    )
    assert up.status_code == 201, up.text
    doc = up.json()
    assert doc["expiry_status"] == "expiring_soon"
    assert doc["has_extracted_text"] is True
    assert "XYZ-9000" in (doc["extracted_preview"] or "")

    # 2) Busca no Cofre encontra termos que existem apenas dentro do PDF extraído.
    found = client.get("/api/cofre/documents", params={"q": "FrostFree"})
    assert found.status_code == 200
    assert len(found.json()["documents"]) == 1
    assert found.json()["summary"]["expiring_count"] == 1

    # 3) Agenda Unificada 360° inclui a 6ª camada ("cofre") com a data de validade.
    tl = client.get(
        "/api/agenda/timeline",
        params={"start": date.today().isoformat(), "end": exp_date, "layers": "cofre"},
    )
    assert tl.status_code == 200
    assert any(it["layer"] == "cofre" and "Geladeira" in it["title"] for it in tl.json()["items"])

    # 4) Download autenticado devolve PDF seguro + nosniff.
    dl = client.get(doc["file_url"])
    assert dl.status_code == 200
    assert dl.content.startswith(b"%PDF-")
    assert dl.headers.get("x-content-type-options") == "nosniff"

    # 5) Rejeita SVG e HTML disfarçados de PNG.
    for bad_name, bad_bytes in (
        ("evil.png", b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'),
        ("evil.pdf", b"<html><script>alert(1)</script></html>"),
    ):
        bad = client.post(
            "/api/cofre/documents",
            files={"file": (bad_name, bad_bytes, "image/png")},
            data={"title": "Malicioso"},
        )
        assert bad.status_code in (400, 415, 422)

    # 6) Ponte Propostas -> Cofre arquiva o PDF A4 de forma idempotente.
    prop = client.post(
        "/api/proposals",
        json={
            "doc_type": "contract",
            "title": "Contrato Manutenção Anual",
            "customer_name": "Padaria Aurora",
            "items": [{"name": "Suporte mensal", "qty": 1, "unit_price": "350.00"}],
        },
    )
    assert prop.status_code == 201
    prop_id = prop.json()["id"]
    arch1 = client.post(f"/api/cofre/from-proposal/{prop_id}")
    arch2 = client.post(f"/api/cofre/from-proposal/{prop_id}")
    assert arch1.status_code == 201
    assert arch1.json()["archived"] is True
    assert arch2.status_code == 201
    assert arch2.json()["archived"] is False
    assert arch1.json()["document"]["id"] == arch2.json()["document"]["id"]

    # 7) Ponte Mensageria -> Cofre protege imagem antiga contra limpeza semanal de 7 dias.
    chat = MessagingChat(
        user_id=user_a.id,
        remote_jid="5511966665555@s.whatsapp.net",
        phone="5511966665555",
        name="Fornecedor Claro",
    )
    db.add(chat)
    db.flush()
    old_ts = chat.created_at - timedelta(days=10)
    media = MessagingMedia(
        user_id=user_a.id,
        kind="image",
        mime_type="image/png",
        file_name="nota-cabo.png",
        size_bytes=len(_png_bytes()),
        data=_png_bytes(),
        created_at=old_ts,
    )
    db.add(media)
    db.flush()
    db.add(
        MessagingMessage(
            user_id=user_a.id,
            chat_id=chat.id,
            direction="in",
            body="Segue nota da garantia",
            message_type="image",
            media_id=media.id,
            created_at=old_ts,
            updated_at=old_ts,
        )
    )
    db.commit()

    arch_wa = client.post(f"/api/cofre/from-messaging/{media.id}")
    assert arch_wa.status_code == 201, arch_wa.text
    vault_wa_id = uuid.UUID(arch_wa.json()["document"]["id"])

    # Roda a limpeza semanal da Mensageria: mídia temporária some, mas documento do Cofre permanece!
    cleaned = purge_old(db)
    db.commit()
    assert cleaned["media"] >= 1
    staying = client.get("/api/cofre/documents")
    assert staying.status_code == 200
    assert any(item["id"] == str(vault_wa_id) for item in staying.json()["documents"])

    # 8) Isolamento estrito entre contas (IDOR retorna 404).
    client.post("/api/auth/logout")
    assert login(client, user_b.email).status_code == 200
    assert client.get(f"/api/cofre/documents/{doc['id']}/file").status_code == 404
    upd_b = client.patch(f"/api/cofre/documents/{doc['id']}", json={"title": "Hack"})
    assert upd_b.status_code == 404
    assert client.delete(f"/api/cofre/documents/{doc['id']}").status_code == 404

    # 9) Bloqueio de solução pelo admin bloqueia rotas do Cofre e oculta camada da Agenda.
    client.post("/api/auth/logout")
    assert login(client, adm.email).status_code == 200
    assert (
        client.patch(
            f"/api/admin/users/{user_a.id}/permissions",
            json={"blocked_resources": ["cofre"], "storage_quota_mb": 200},
        ).status_code
        == 200
    )
    client.post("/api/auth/logout")
    assert login(client, user_a.email).status_code == 200
    assert client.get("/api/cofre/documents").status_code == 403
    tl_blocked = client.get(
        "/api/agenda/timeline",
        params={"start": date.today().isoformat(), "end": exp_date},
    )
    assert tl_blocked.status_code == 200
    assert all(it["layer"] != "cofre" for it in tl_blocked.json()["items"])


def test_notebook_bm25_wikilinks_backlinks_bridges_and_isolation(
    client: TestClient, db: Session, outbox: list
) -> None:
    adm = _make_user(client, db, outbox, "admin_cad@example.com", is_admin=True)
    user_a = _make_user(client, db, outbox, "caderno_a@example.com")
    user_b = _make_user(client, db, outbox, "caderno_b@example.com")

    assert login(client, user_a.email).status_code == 200

    tpls = client.get("/api/caderno/templates")
    assert tpls.status_code == 200
    assert any(t["id"] == "sales_script" for t in tpls.json())

    # Cria duas notas ligadas por wikilink [[Roteiro Comercial]].
    n1 = client.post(
        "/api/caderno/notes",
        json={
            "title": "Roteiro Comercial",
            "folder": "Comercial",
            "tags": ["whatsapp", "vendas"],
            "pinned": True,
            "template_kind": "sales_script",
            "content": (
                "# Roteiro Oficial\nUsar em novos leads de energia solar com desconto à vista."
            ),
        },
    )
    assert n1.status_code == 201
    n1_id = n1.json()["id"]

    n2 = client.post(
        "/api/caderno/notes",
        json={
            "title": "Checklist Pós-Venda",
            "folder": "Operação",
            "tags": ["entrega"],
            "content": "Antes de fechar, revisar [[Roteiro Comercial]] e arquivar contrato.",
        },
    )
    assert n2.status_code == 201
    n2_data = n2.json()
    assert n2_data["links"][0]["target_id"] == n1_id

    # Busca BM25 ordena corretamente e traz backlinks na nota alvo.
    search_res = client.get("/api/caderno/notes", params={"q": "energia solar"})
    assert search_res.status_code == 200
    found = search_res.json()["notes"]
    assert len(found) == 1
    assert found[0]["id"] == n1_id
    assert found[0]["backlinks"][0]["title"] == "Checklist Pós-Venda"

    # Conta B não lê, edita nem exclui nota de A.
    client.post("/api/auth/logout")
    assert login(client, user_b.email).status_code == 200
    assert (
        client.patch(f"/api/caderno/notes/{n1_id}", json={"title": "Invadida"}).status_code == 404
    )
    assert client.delete(f"/api/caderno/notes/{n1_id}").status_code == 404
    # Tentar ligar nota de B ao note/projeto de A falha 404.
    assert (
        client.post(
            "/api/caderno/notes",
            json={"title": "Nota B", "content": "x", "vault_doc_id": str(uuid.uuid4())},
        ).status_code
        == 404
    )

    # Admin bloqueia Caderno -> 403.
    client.post("/api/auth/logout")
    assert login(client, adm.email).status_code == 200
    assert (
        client.patch(
            f"/api/admin/users/{user_a.id}/permissions",
            json={"blocked_resources": ["caderno"], "storage_quota_mb": 200},
        ).status_code
        == 200
    )
    client.post("/api/auth/logout")
    assert login(client, user_a.email).status_code == 200
    assert client.get("/api/caderno/notes").status_code == 403


def test_projects_d3_exclusive_budget_tag_prevents_collision(
    client: TestClient, db: Session, outbox: list
) -> None:
    user = _make_user(client, db, outbox, "d3_proj@example.com")
    assert login(client, user.email).status_code == 200

    # Já existe uma etiqueta pessoal "Reforma" no Meu Orçamento com gasto prévio.
    month = date.today().replace(day=1)
    ensure_month(db, user, month)
    old_tag = Project(user_id=user.id, name="Reforma")
    db.add(old_tag)
    db.flush()
    db.add(
        Expense(
            user_id=user.id,
            month=month,
            description="Tinta pessoal",
            amount=400,
            due_date=date.today(),
            paid=True,
            project_id=old_tag.id,
        )
    )
    db.commit()

    # Criar projeto "Reforma" sem passar budget_project_id cria etiqueta exclusiva e isola gastos.
    res = client.post(
        "/api/work/projects",
        json={"name": "Reforma", "budget_value": "1500.00", "link_budget_tag": True},
    )
    assert res.status_code == 201
    proj = res.json()
    assert proj["budget_project_id"] is not None
    assert proj["budget_project_id"] != str(old_tag.id)
    assert proj["expenses_total"] == "0.00"
