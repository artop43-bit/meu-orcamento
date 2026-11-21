"""Testes do Dashboard & CRM integrado ao Hub (PDF/OCR, CSV, API anti-SSRF, pontes e painéis)."""

from __future__ import annotations

import io
import json
import uuid
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from fpdf import FPDF
from PIL import Image, ImageDraw
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.months import current_month
from app.models import Income, MessagingChat, User
from app.services.crm import api_connector
from app.services.crm.pdf_reader import extract_pdf
from tests.conftest import create_verified_user, login


def _auth(client: TestClient, outbox: list, email: str = "crm@example.com") -> None:
    create_verified_user(client, outbox, email)
    assert login(client, email).status_code == 200


def _make_table_pdf() -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 11)
    headers = ["Cliente", "Telefone", "Valor", "Data"]
    widths = [45, 45, 35, 35]
    for w, h in zip(widths, headers, strict=True):
        pdf.cell(w, 8, h, border=1)
    pdf.ln()
    pdf.set_font("Helvetica", "", 10)
    rows = [
        ["Ana Souza", "(11) 98765-4321", "R$ 1.500,00", "10/11/2026"],
        ["Bruno Lima", "(21) 99999-1111", "R$ 2.750,50", "12/11/2026"],
    ]
    for r in rows:
        for w, val in zip(widths, r, strict=True):
            pdf.cell(w, 8, val, border=1)
        pdf.ln()
    return bytes(pdf.output())


def _make_scanned_pdf(tmp_path: Path) -> bytes:
    img = Image.new("RGB", (900, 320), "white")
    draw = ImageDraw.Draw(img)
    draw.text((40, 40), "Cliente: Carla Mendes", fill="black")
    draw.text((40, 90), "Email: carla@empresa.com", fill="black")
    draw.text((40, 140), "Valor: R$ 3.200,00", fill="black")
    img_path = tmp_path / "scan.png"
    img.save(img_path)

    pdf = FPDF()
    pdf.add_page()
    pdf.image(str(img_path), x=10, y=10, w=180)
    return bytes(pdf.output())


def test_crm_requires_auth(client: TestClient) -> None:
    assert client.get("/api/crm/dashboards").status_code == 401
    assert client.get("/api/crm/pipeline").status_code == 401
    assert client.get("/api/crm/sources").status_code == 401


def test_pdf_reader_table_and_scanned_ocr(tmp_path: Path) -> None:
    table_res = extract_pdf(_make_table_pdf(), "vendas.pdf")
    assert table_res.strategy == "tabela_pdf"
    assert table_res.used_ocr is False
    assert len(table_res.rows) == 2
    assert table_res.rows[0]["cliente"] == "Ana Souza"
    assert table_res.rows[0]["valor"] == 1500.0

    scan_res = extract_pdf(_make_scanned_pdf(tmp_path), "escaneado.pdf")
    assert scan_res.used_ocr is True
    assert scan_res.ocr_pages == 1
    assert len(scan_res.rows) >= 1


@pytest.mark.parametrize(
    "bad_url",
    [
        "http://example.com/data",
        "https://localhost/api",
        "https://127.0.0.1/api",
        "https://169.254.169.254/latest/meta-data/",
        "https://10.0.0.1/api",
        "https://user:pass@example.com/api",
    ],
)
def test_api_connector_blocks_ssrf(bad_url: str) -> None:
    with pytest.raises(Exception) as exc:
        api_connector.validate_api_url(bad_url)
    assert exc.value is not None


def test_api_source_encrypts_credentials_and_syncs(
    client: TestClient, outbox: list, monkeypatch: pytest.MonkeyPatch
) -> None:
    _auth(client, outbox)
    monkeypatch.setattr(api_connector, "_resolve_ips", lambda host, port: ["93.184.216.34"])

    payload = json.dumps(
        {"data": {"items": [{"produto": "Plano Pro", "valor": "R$ 490,00", "data": "2026-11-15"}]}}
    ).encode("utf-8")

    class _FakeResp(io.BytesIO):
        status = 200

        def __enter__(self) -> _FakeResp:
            return self

        def __exit__(self, *args: Any) -> None:
            return None

    class _FakeOpener:
        def open(self, req: Any, timeout: int = 10) -> _FakeResp:
            assert req.headers.get("Authorization") == "Bearer segredo-123"
            return _FakeResp(payload)

    monkeypatch.setattr(api_connector, "build_opener", lambda *args: _FakeOpener())

    res = client.post(
        "/api/crm/sources/api",
        json={
            "name": "API Vendas",
            "url": "https://api.exemplo.com/vendas",
            "data_path": "data.items",
            "auth_type": "bearer",
            "auth_value": "segredo-123",
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["has_credentials"] is True
    assert "segredo-123" not in json.dumps(body)
    assert body["row_count"] == 1

    sync = client.post(f"/api/crm/sources/{body['id']}/sync")
    assert sync.status_code == 200
    assert sync.json()["row_count"] == 1


def test_crm_hub_native_integration_and_isolation(
    client: TestClient, outbox: list, db: Session
) -> None:
    _auth(client, outbox, "ana@example.com")

    # Cria conversa real na Mensageria e importa para o CRM.
    chat = client.post(
        "/api/messaging/chats",
        json={"phone": "11988887777", "name": "Marina Costa", "budget_person": "Marina"},
    ).json()
    imp = client.post(f"/api/crm/contacts/from-messaging/{chat['id']}")
    assert imp.status_code == 200, imp.text
    contact = imp.json()["contact"]
    assert imp.json()["created"] is True
    assert contact["messaging_chat_id"] == chat["id"]
    assert contact["name"] == "Marina Costa"
    # Segunda chamada é idempotente.
    imp2 = client.post(f"/api/crm/contacts/from-messaging/{chat['id']}")
    assert imp2.json()["created"] is False
    assert imp2.json()["contact"]["id"] == contact["id"]

    # Cria negócio no funil (com vírgula BR), move para Ganho e lança receita REAL no Orçamento.
    board = client.get("/api/crm/pipeline").json()
    won_stage = next(s for s in board["stages"] if s["is_won"])
    deal = client.post(
        "/api/crm/deals",
        json={
            "title": "Consultoria Anual",
            "value": "4.800,00",
            "contact_id": contact["id"],
            "stage_id": won_stage["id"],
        },
    ).json()
    assert deal["status"] == "won"

    synced = client.post(f"/api/crm/deals/{deal['id']}/sync-budget")
    assert synced.status_code == 200, synced.text
    income_id = uuid.UUID(synced.json()["budget_income_id"])
    db.expire_all()
    inc = db.get(Income, income_id)
    assert inc is not None
    assert inc.description == "CRM: Consultoria Anual"
    assert float(inc.amount) == 4800.0
    user = db.scalar(select(User).where(User.email == "ana@example.com"))
    assert user is not None
    assert inc.month == current_month(user.month_start_day)

    # As 4 fontes nativas do Hub existem e leem dados reais (CRM, Contatos, Mensageria, Orçamento).
    sources = client.get("/api/crm/sources").json()
    kinds = {s["kind"]: s for s in sources}
    assert {"native_crm", "native_crm_contacts", "native_messaging", "native_budget"} <= set(kinds)
    assert kinds["native_crm"]["row_count"] == 1
    assert kinds["native_budget"]["row_count"] >= 1

    # Sobe PDF de vendas, salva fonte e gera painel automático.
    prev = client.post(
        "/api/crm/sources/preview/pdf",
        files={"file": ("vendas.pdf", _make_table_pdf(), "application/pdf")},
    )
    assert prev.status_code == 200, prev.text
    pdf_data = prev.json()
    saved = client.post(
        "/api/crm/sources/tabular",
        json={
            "name": "Relatório PDF",
            "kind": "pdf",
            "columns": pdf_data["columns"],
            "rows": pdf_data["rows"],
            "create_dashboard": True,
        },
    )
    assert saved.status_code == 201, saved.text
    dash = saved.json()["dashboard"]
    assert dash is not None
    assert len(dash["widgets"]) >= 3

    # Modelos nativos (Mensageria e Meu Orçamento).
    msg_dash = client.post(
        "/api/crm/dashboards", json={"name": "Painel WhatsApp", "template": "messaging_overview"}
    )
    assert msg_dash.status_code == 201
    budget_dash = client.post(
        "/api/crm/dashboards", json={"name": "Painel Orçamento", "template": "budget_overview"}
    )
    assert budget_dash.status_code == 201

    # CSV com ponto-e-vírgula e importação direta para contatos.
    csv_bytes = b"Nome;Telefone;Empresa\nLucas Reis;11977776666;Reis Tech\n"
    csv_prev = client.post(
        "/api/crm/sources/preview/csv",
        files={"file": ("leads.csv", csv_bytes, "text/csv")},
    )
    assert csv_prev.status_code == 200
    imp_crm = client.post(
        "/api/crm/sources/import-to-crm",
        json={
            "target": "contacts",
            "rows": csv_prev.json()["rows"],
            "mapping": csv_prev.json()["suggestions"]["contact_mapping"],
        },
    )
    assert imp_crm.status_code == 200
    assert imp_crm.json()["created"] == 1

    # Isolamento entre usuários: outro usuário não vê contatos, fontes nem painéis da Ana.
    client.post("/api/auth/logout")
    _auth(client, outbox, "bruno@example.com")
    assert client.get("/api/crm/contacts").json() == []
    assert client.get(f"/api/crm/dashboards/{dash['id']}").status_code == 404
    assert client.delete(f"/api/crm/contacts/{contact['id']}").status_code == 404
    assert db.scalar(select(MessagingChat).where(MessagingChat.id == uuid.UUID(chat["id"])))
    assert date.today().year >= 2026
