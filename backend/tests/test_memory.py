"""Testes da Fase D: Cofre de Documentos (`/cofre`), Caderno (`/caderno`) e pontes 360°."""

from __future__ import annotations

import io
import uuid
from datetime import date, timedelta

import pymupdf
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import event, inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.models import (
    Expense,
    MessagingChat,
    MessagingMedia,
    MessagingMessage,
    Project,
    User,
    VaultDocument,
)
from app.services.budget import ensure_month
from app.services.memory import vault as vault_service
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
    assert arch2.status_code == 200
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


def test_vault_listing_agenda_and_bridges_do_not_load_binary_payload(
    client: TestClient, db: Session, engine: Engine, outbox: list
) -> None:
    user = _make_user(client, db, outbox, "cofre_deferred@example.com")
    assert login(client, user.email).status_code == 200

    pdf = _pdf_bytes("Manual Garantia TV OLED 65")
    exp_date = (date.today() + timedelta(days=5)).isoformat()
    up = client.post(
        "/api/cofre/documents",
        files={"file": ("manual-tv.pdf", pdf, "application/pdf")},
        data={"title": "Manual TV", "category": "warranty", "expires_at": exp_date},
    )
    assert up.status_code == 201, up.text
    doc_id = uuid.UUID(up.json()["id"])

    db.expunge_all()
    loaded = db.scalar(select(VaultDocument).where(VaultDocument.id == doc_id))
    assert loaded is not None
    assert "data" in inspect(loaded).unloaded
    vault_service._serialize(loaded, date.today())
    assert "data" in inspect(loaded).unloaded

    seen_sql: list[str] = []

    def _capture(_conn, _cursor, statement: str, *_args) -> None:  # type: ignore[no-untyped-def]
        if statement.lstrip().upper().startswith("SELECT"):
            seen_sql.append(statement)

    event.listen(engine, "before_cursor_execute", _capture)
    try:
        listed = client.get("/api/cofre/documents")
        assert listed.status_code == 200
        assert len(listed.json()["documents"]) == 1
        tl = client.get(
            "/api/agenda/timeline",
            params={"start": date.today().isoformat(), "end": exp_date, "layers": "cofre"},
        )
        assert tl.status_code == 200
        bridges = client.get("/api/caderno/hub/bridges")
        assert bridges.status_code == 200
        assert len(bridges.json()["vault_docs"]) == 1
    finally:
        event.remove(engine, "before_cursor_execute", _capture)

    assert seen_sql
    assert all("vault_documents.data" not in stmt.lower() for stmt in seen_sql)

    dl = client.get(f"/api/cofre/documents/{doc_id}/file")
    assert dl.status_code == 200
    assert dl.content == pdf


def test_vault_image_rule_6mb_4000px_strips_exif_and_rejects_svg(
    client: TestClient, db: Session, outbox: list
) -> None:
    from app.core.errors import AppError
    from app.services import files

    user = _make_user(client, db, outbox, "cofre_img_r2@example.com")
    assert login(client, user.email).status_code == 200

    # 1) Imagem ~6 MB (acima da regra antiga de 5 MB) é aceita pelo Cofre.
    noisy = Image.effect_noise((2200, 2200), 90).convert("RGB")
    buf_6mb = io.BytesIO()
    noisy.save(buf_6mb, format="JPEG", quality=100, subsampling=0)
    raw_6mb = buf_6mb.getvalue()
    assert 5 * 1024 * 1024 < len(raw_6mb) <= 15 * 1024 * 1024
    up_big = client.post(
        "/api/cofre/documents",
        files={"file": ("nota-grande.jpg", raw_6mb, "image/jpeg")},
        data={"title": "Foto 6 MB"},
    )
    assert up_big.status_code == 201, up_big.text
    assert up_big.json()["mime_type"] == "image/jpeg"

    # 2) Imagem de 4000 px mantém 4000 px e perde EXIF GPS na regravação.
    hi_res = Image.new("RGB", (4000, 120), (200, 120, 40))
    exif = hi_res.getexif()
    exif[271] = "CameraTeste"
    exif[34853] = {1: "S", 2: (23.0, 33.0, 0.0)}
    buf_4k = io.BytesIO()
    hi_res.save(buf_4k, format="JPEG", quality=95, exif=exif.tobytes())
    up_4k = client.post(
        "/api/cofre/documents",
        files={"file": ("garantia-4k.jpg", buf_4k.getvalue(), "image/jpeg")},
        data={"title": "Foto 4000 px"},
    )
    assert up_4k.status_code == 201, up_4k.text
    dl_4k = client.get(up_4k.json()["file_url"])
    assert dl_4k.status_code == 200
    with Image.open(io.BytesIO(dl_4k.content)) as out_img:
        assert out_img.format == "JPEG"
        assert out_img.size == (4000, 120)
        assert dict(out_img.getexif()) == {}
        assert "exif" not in out_img.info

    # 3) PNG mantém formato sem perda.
    png_img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    png_img.putpixel((10, 10), (12, 34, 56, 255))
    buf_png = io.BytesIO()
    png_img.save(buf_png, format="PNG")
    prepared_png, ctype_png, w_png, h_png = files.prepare(buf_png.getvalue(), "vault")
    assert ctype_png == "image/png"
    assert (w_png, h_png) == (64, 64)
    with Image.open(io.BytesIO(prepared_png)) as out_png:
        assert out_png.format == "PNG"
        assert out_png.convert("RGBA").getpixel((10, 10)) == (12, 34, 56, 255)
        assert out_png.convert("RGBA").getpixel((0, 0))[3] == 0

    # 4) SVG recusado na preparação e no endpoint.
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    try:
        files.prepare(svg, "vault")
    except AppError as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError("SVG deveria ter sido rejeitado")
    bad_svg = client.post(
        "/api/cofre/documents",
        files={"file": ("vetor.svg", svg, "image/svg+xml")},
        data={"title": "SVG"},
    )
    assert bad_svg.status_code == 400

    # 5) Arquivo acima de 15 MB é rejeitado antes de salvar.
    too_big = client.post(
        "/api/cofre/documents",
        files={"file": ("gigante.jpg", b"x" * (15 * 1024 * 1024 + 1), "image/jpeg")},
        data={"title": "Grande demais"},
    )
    assert too_big.status_code == 413


def test_vault_upload_rate_limit_and_ocr_busy_stops_early(
    client: TestClient, db: Session, outbox: list, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.errors import AppError
    from app.services import ocr as receipt_ocr

    user = _make_user(client, db, outbox, "cofre_r3@example.com")
    assert login(client, user.email).status_code == 200

    # 1) PDF escaneado com 3 páginas quando OCR está ocupado: para na 1ª tentativa e retorna aviso.
    doc = pymupdf.open()
    for _ in range(3):
        doc.new_page()
    blank_pdf = doc.tobytes()
    doc.close()

    ocr_calls = 0

    expected_warning = (
        "Documento guardado. A leitura do texto não foi feita agora; "
        "tente enviar de novo mais tarde."
    )

    def busy_ocr_page(_page: object) -> str:
        nonlocal ocr_calls
        ocr_calls += 1
        raise AppError(
            503, "ocr_busy", "Muitas leituras ao mesmo tempo. Tente de novo em instantes."
        )

    monkeypatch.setattr(receipt_ocr, "available", lambda: True)
    monkeypatch.setattr(vault_service, "_ocr_page", busy_ocr_page)

    res_pdf = client.post(
        "/api/cofre/documents",
        files={"file": ("escaneado.pdf", blank_pdf, "application/pdf")},
        data={"title": "PDF OCR Ocupado"},
    )
    assert res_pdf.status_code == 201, res_pdf.text
    body_pdf = res_pdf.json()
    assert ocr_calls == 1
    assert body_pdf["ocr_used"] is False
    assert body_pdf["has_extracted_text"] is False
    assert body_pdf["warning"] == expected_warning

    # 2) Imagem quando OCR está ocupado também salva sem texto e devolve o aviso.
    def busy_extract(_raw: bytes) -> object:
        raise AppError(
            503, "ocr_busy", "Muitas leituras ao mesmo tempo. Tente de novo em instantes."
        )

    monkeypatch.setattr(receipt_ocr, "extract", busy_extract)
    res_img = client.post(
        "/api/cofre/documents",
        files={"file": ("foto.png", _png_bytes(), "image/png")},
        data={"title": "PNG OCR Ocupado"},
    )
    assert res_img.status_code == 201, res_img.text
    body_img = res_img.json()
    assert body_img["ocr_used"] is False
    assert body_img["has_extracted_text"] is False
    assert body_img["warning"] == expected_warning

    # 3) Rate limit: 5 uploads por minuto liberados (já fizemos 2 acima), 6º retorna 429.
    small_pdf = _pdf_bytes("Texto digital suficiente para nao precisar de OCR.")
    for i in range(3):
        ok = client.post(
            "/api/cofre/documents",
            files={"file": (f"ok-{i}.pdf", small_pdf, "application/pdf")},
            data={"title": f"Doc {i}"},
        )
        assert ok.status_code == 201, ok.text

    blocked = client.post(
        "/api/cofre/documents",
        files={"file": ("sexto.pdf", small_pdf, "application/pdf")},
        data={"title": "Sexto"},
    )
    assert blocked.status_code == 429
    assert blocked.json()["error"] == "rate_limited"


def test_notebook_list_limit_excerpt_and_get_full_note(
    client: TestClient, db: Session, outbox: list
) -> None:
    user_a = _make_user(client, db, outbox, "caderno_r4_a@example.com")
    user_b = _make_user(client, db, outbox, "caderno_r4_b@example.com")
    assert login(client, user_a.email).status_code == 200

    long_text = "Linha inicial do roteiro comercial. " + ("detalhe " * 50)
    assert len(long_text) > 250

    created_ids: list[str] = []
    for idx in range(25):
        res = client.post(
            "/api/caderno/notes",
            json={
                "title": f"Nota {idx:02d}",
                "folder": "Comercial",
                "content": long_text,
            },
        )
        assert res.status_code == 201, res.text
        created_ids.append(res.json()["id"])

    # Padrão limit=20 e lista traz só excerpt (<= 200 chars), sem content completo.
    listed = client.get("/api/caderno/notes")
    assert listed.status_code == 200
    data = listed.json()
    assert len(data["notes"]) == 20
    assert data["summary"]["total_notes"] == 25
    for item in data["notes"]:
        assert "content" not in item
        assert len(item["excerpt"]) <= 200
        assert item["excerpt"].startswith("Linha inicial do roteiro")

    assert len(client.get("/api/caderno/notes", params={"limit": 5}).json()["notes"]) == 5
    assert len(client.get("/api/caderno/notes", params={"limit": 50}).json()["notes"]) == 25
    assert client.get("/api/caderno/notes", params={"limit": 51}).status_code == 422

    # Rota individual GET /api/caderno/notes/{id} entrega o conteúdo inteiro e isola por dono.
    full = client.get(f"/api/caderno/notes/{created_ids[-1]}")
    assert full.status_code == 200
    assert full.json()["content"] == long_text

    client.post("/api/auth/logout")
    assert login(client, user_b.email).status_code == 200
    assert client.get(f"/api/caderno/notes/{created_ids[-1]}").status_code == 404


def test_vault_double_click_and_unique_index_prevent_duplicates(
    client: TestClient, db: Session, outbox: list, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sqlalchemy import func

    from app.services import admin as admin_service

    user = _make_user(client, db, outbox, "cofre_r5@example.com")
    assert login(client, user.email).status_code == 200

    media = MessagingMedia(
        user_id=user.id,
        kind="image",
        mime_type="image/png",
        file_name="recibo-wa.png",
        size_bytes=len(_png_bytes()),
        data=_png_bytes(),
    )
    db.add(media)
    db.commit()

    # 1) Duas chamadas seguidas em from-messaging resultam em 1 documento e 1 contagem na cota.
    first = client.post(f"/api/cofre/from-messaging/{media.id}")
    assert first.status_code == 201, first.text
    assert first.json()["archived"] is True
    used_after_first = admin_service.user_storage_bytes(db, user.id)

    second = client.post(f"/api/cofre/from-messaging/{media.id}")
    assert second.status_code == 200, second.text
    assert second.json()["archived"] is False
    assert second.json()["document"]["id"] == first.json()["document"]["id"]
    assert admin_service.user_storage_bytes(db, user.id) == used_after_first
    count_wa = db.scalar(
        select(func.count()).where(
            VaultDocument.user_id == user.id,
            VaultDocument.messaging_media_id == media.id,
        )
    )
    assert count_wa == 1

    # 2) Corrida simultânea: pré-checagem passa vazia, índice único barra e retorna 200.
    prop = client.post(
        "/api/proposals",
        json={
            "doc_type": "proposal",
            "title": "Proposta Duplo Clique",
            "customer_name": "Cliente R5",
            "items": [{"name": "Item", "qty": 1, "unit_price": "100.00"}],
        },
    ).json()
    prop_id = prop["id"]
    p1 = client.post(f"/api/cofre/from-proposal/{prop_id}")
    assert p1.status_code == 201

    orig_create = vault_service.create_document

    def race_create(session: Session, owner: User, **kwargs: object) -> dict[str, object]:
        # Simula que a requisição concorrente passou da pré-checagem antes do primeiro commit.
        return orig_create(session, owner, **kwargs)  # type: ignore[arg-type]

    orig_scalar = Session.scalar
    skipped_once = False

    def skip_precheck(self: Session, statement: object, *args: object, **kwargs: object) -> object:
        nonlocal skipped_once
        if not skipped_once and "vault_documents.proposal_id" in str(statement):
            skipped_once = True
            return None
        return orig_scalar(self, statement, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(vault_service, "create_document", race_create)
    monkeypatch.setattr(Session, "scalar", skip_precheck)
    p2 = client.post(f"/api/cofre/from-proposal/{prop_id}")
    assert p2.status_code == 200, p2.text
    assert p2.json()["archived"] is False
    assert p2.json()["document"]["id"] == p1.json()["document"]["id"]
    count_prop = db.scalar(
        select(func.count()).where(
            VaultDocument.user_id == user.id,
            VaultDocument.proposal_id == uuid.UUID(prop_id),
        )
    )
    assert count_prop == 1
