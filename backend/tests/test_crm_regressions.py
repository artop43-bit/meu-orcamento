"""Regressões da revisão aprovada do CRM: valores, isolamento, períodos e conectores."""

import importlib.util
import io
import math
import ssl
import time
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    SmallInteger,
    Table,
    create_engine,
    inspect,
    select,
)

from app.core.errors import AppError
from app.core.months import current_month
from app.models import CrmActivity, CrmContact, Expense, Income, User
from app.services.crm import api_connector, csv_reader, hub_bridge, pdf_reader, query_engine
from app.services.crm.parsing import coerce_cell, parse_money, parse_number
from tests.conftest import create_verified_user, login


def _auth(client, outbox, email="crm-revisao@example.com"):
    create_verified_user(client, outbox, email)
    assert login(client, email).status_code == 200


@pytest.mark.parametrize(
    "raw", ["NaN", "sNaN", "Infinity", "-Infinity", "1e400", "-1", "10000000000"]
)
def test_deal_rejects_invalid_money(client, outbox, raw):
    _auth(client, outbox)
    response = client.post("/api/crm/deals", json={"title": "Teste", "value": raw})
    assert response.status_code == 422
    assert parse_money(raw) is None


@pytest.mark.parametrize("raw", ["NaN", "Infinity", "1e400", float("nan")])
def test_nonfinite_dataset_cell_is_empty(raw):
    assert parse_number(raw) is None
    assert coerce_cell(raw, "currency") is None


def test_query_period_brasilia_missing_future_and_boundary(monkeypatch):
    monkeypatch.setattr(query_engine, "today_local", lambda: date(2026, 11, 20))
    result = query_engine.run_widget_query(
        schema=[{"name": "data", "type": "date"}, {"name": "valor", "type": "currency"}],
        rows=[
            {"data": d, "valor": v}
            for d, v in [
                (None, 100),
                ("2026-11-21", 200),
                ("2026-11-13", 400),
                ("2026-11-14", 5),
                ("2026-11-20", 7),
            ]
        ],
        widget_type="kpi",
        query={"metric": "sum", "value_field": "valor"},
        date_range="7d",
    )
    assert result["count"] == 2
    assert result["value"] == 12
    no_dates = query_engine.run_widget_query(
        schema=[{"name": "valor", "type": "number"}],
        rows=[{"valor": 5}],
        widget_type="kpi",
        query={},
        date_range="month",
    )
    assert no_dates["count"] == 0


def test_malformed_query_and_csv_are_controlled():
    result = query_engine.run_widget_query(
        schema=[], rows=[], widget_type="bar", query={"limit": "abc", "filters": "abc"}
    )
    assert len(result["warnings"]) == 2
    with pytest.raises(AppError) as err:
        csv_reader.extract_csv(b"Nome;Valor\nAna;10\n", delimiter=";;")
    assert err.value.code == "invalid_delimiter"
    dataset = csv_reader.extract_csv("Descrição;Valor\nServiço;1.234,56\n".encode("latin-1"))
    assert dataset["rows"][0]["valor"] == 1234.56


def test_sync_budget_won_once_current_month_and_brl(client, outbox, db):
    _auth(client, outbox)
    stages = client.get("/api/crm/pipeline").json()["stages"]
    deal = client.post(
        "/api/crm/deals",
        json={"title": "Serviço", "value": "4.800,00", "expected_close_date": "2030-12-10"},
    ).json()
    rejected = client.post(f"/api/crm/deals/{deal['id']}/sync-budget")
    assert rejected.status_code == 409
    won = next(stage for stage in stages if stage["is_won"])
    moved = client.patch(f"/api/crm/deals/{deal['id']}", json={"stage_id": won["id"]})
    assert moved.json()["status"] == "won"
    first = client.post(f"/api/crm/deals/{deal['id']}/sync-budget")
    second = client.post(f"/api/crm/deals/{deal['id']}/sync-budget")
    assert first.status_code == second.status_code == 200
    assert first.json()["budget_income_id"] == second.json()["budget_income_id"]
    db.expire_all()
    income = db.get(Income, uuid.UUID(first.json()["budget_income_id"]))
    user = db.scalar(select(User).where(User.email == "crm-revisao@example.com"))
    assert income.month == current_month(user.month_start_day)
    assert len(db.scalars(select(Income).where(Income.description == "CRM: Serviço")).all()) == 1
    activity = db.scalar(
        select(CrmActivity).where(
            CrmActivity.deal_id == uuid.UUID(deal["id"]), CrmActivity.kind == "budget"
        )
    )
    assert "R$ 4.800,00" in activity.body.replace("\xa0", " ")


def test_import_bad_money_skips_rows(client, outbox):
    _auth(client, outbox)
    response = client.post(
        "/api/crm/sources/import-to-crm",
        json={
            "target": "deals",
            "mapping": {"title": "titulo", "value": "valor"},
            "rows": [
                {"titulo": "ruim", "valor": "NaN"},
                {"titulo": "negativo", "valor": "-10"},
                {"titulo": "bom", "valor": "100,50"},
            ],
        },
    )
    assert response.status_code == 200
    assert response.json() == {"created": 1, "skipped": 2}
    assert client.get("/api/crm/pipeline").status_code == 200


def test_source_widget_other_account_isolation(client, outbox):
    _auth(client, outbox)
    sources = client.get("/api/crm/sources").json()
    source_id = sources[0]["id"]
    dashboard = client.post(
        "/api/crm/dashboards", json={"name": "Privado", "template": "crm_overview"}
    ).json()
    widget_id = dashboard["widgets"][0]["id"]
    client.post("/api/auth/logout")
    _auth(client, outbox, "crm-outra@example.com")
    assert client.get(f"/api/crm/sources/{source_id}/rows").status_code == 404
    assert client.post(f"/api/crm/sources/{source_id}/sync").status_code == 404
    assert client.patch(f"/api/crm/widgets/{widget_id}", json={"title": "Outro"}).status_code == 404
    assert client.delete(f"/api/crm/widgets/{widget_id}").status_code == 404


def test_native_budget_no_truncation_and_contact_local_date(client, outbox, db):
    _auth(client, outbox)
    user = db.scalar(select(User).where(User.email == "crm-revisao@example.com"))
    month = date(2026, 11, 1)
    db.add_all(
        [
            Income(user_id=user.id, month=month, description=f"Receita {i}", amount=Decimal("1"))
            for i in range(1002)
        ]
    )
    db.add_all(
        [
            Expense(user_id=user.id, month=month, description=f"Despesa {i}", amount=Decimal("2"))
            for i in range(2002)
        ]
    )
    db.add(
        CrmContact(
            user_id=user.id, name="Ana", created_at=datetime(2026, 11, 20, 1, 30, tzinfo=UTC)
        )
    )
    db.commit()
    _, rows = hub_bridge.native_budget_dataset(db, user.id)
    assert sum(row["valor"] for row in rows if row["tipo"] == "Receita") == 1002
    assert sum(row["valor"] for row in rows if row["tipo"] == "Despesa") == 4004
    _, contacts = hub_bridge.native_crm_contacts_dataset(db, user.id)
    assert contacts[0]["data"] == "2026-11-19"


@pytest.mark.parametrize(
    "ip",
    [
        "64:ff9b::7f00:1",
        "64:ff9b:1::a00:1",
        "::127.0.0.1",
        "::ffff:192.168.1.1",
        "2002:7f00:0001::1",
        "::1",
        "ff02::1",
    ],
)
def test_connector_blocks_embedded_private_ipv6(ip):
    assert not api_connector._is_public_ip(ip)


def test_connector_pins_tcp_and_keeps_tls_hostname(monkeypatch):
    raw = object()
    tls = SimpleNamespace(do_handshake=lambda: None)
    calls = []
    monkeypatch.setattr(
        api_connector.socket,
        "create_connection",
        lambda address, timeout: (calls.append(address), raw)[1],
    )
    conn = api_connector._PinnedHTTPSConnection(
        "api.exemplo.com", pinned_ip="93.184.216.34", deadline=time.monotonic() + 10, sockets=[]
    )
    assert conn._context.check_hostname is True
    assert conn._context.verify_mode == ssl.CERT_REQUIRED
    conn._context = SimpleNamespace(
        wrap_socket=lambda sock, server_hostname, **kwargs: (calls.append(server_hostname), tls)[1]
    )
    conn.connect()
    assert calls == [("93.184.216.34", 443), "api.exemplo.com"]
    assert conn.sock is tls
    conn.sock = None


def _fake_api(monkeypatch, response):
    monkeypatch.setattr(api_connector, "_resolve_ips", lambda host, port: ["93.184.216.34"])
    monkeypatch.setattr(
        api_connector,
        "build_opener",
        lambda *args: SimpleNamespace(open=lambda *args, **kwargs: response),
    )


class _Response(io.BytesIO):
    status = 200


def test_connector_response_size_redirect_and_total_deadline(monkeypatch):
    _fake_api(monkeypatch, _Response(b"x" * (api_connector.MAX_RESPONSE_BYTES + 1)))
    with pytest.raises(AppError) as err:
        api_connector.fetch_external_api(url="https://example.com/")
    assert err.value.code == "payload_too_large"
    redirect = _Response(b"")
    redirect.status = 302
    _fake_api(monkeypatch, redirect)
    with pytest.raises(AppError) as err:
        api_connector.fetch_external_api(url="https://example.com/")
    assert err.value.code == "redirect_blocked"

    class Slow(_Response):
        def read1(self, size):
            time.sleep(0.02)
            return b" "

    monkeypatch.setattr(api_connector, "REQUEST_TIMEOUT_SECONDS", 0.01)
    _fake_api(monkeypatch, Slow())
    with pytest.raises(AppError) as err:
        api_connector.fetch_external_api(url="https://example.com/")
    assert err.value.code == "api_unreachable"


@pytest.mark.parametrize("status,code", [(302, "redirect_blocked"), (500, "api_http_error")])
def test_connector_http_errors_are_controlled(monkeypatch, status, code):
    monkeypatch.setattr(api_connector, "_resolve_ips", lambda host, port: ["93.184.216.34"])

    def fail(*args, **kwargs):
        raise HTTPError("https://example.com/", status, "Erro", {}, None)

    monkeypatch.setattr(api_connector, "build_opener", lambda *args: SimpleNamespace(open=fail))
    with pytest.raises(AppError) as err:
        api_connector.fetch_external_api(url="https://example.com/")
    assert err.value.code == code


def test_connector_does_not_resolve_again_after_validation(monkeypatch):
    calls = []

    def resolve(host, port):
        calls.append(host)
        return ["93.184.216.34"] if len(calls) == 1 else ["127.0.0.1"]

    _fake_api(monkeypatch, _Response(b'[{"valor": 12}]'))
    monkeypatch.setattr(api_connector, "_resolve_ips", resolve)
    assert api_connector.fetch_external_api(url="https://example.com/")["total_rows"] == 1
    assert calls == ["example.com"]


def test_api_rate_limit_and_removed_fields_routes(client, outbox, monkeypatch):
    _auth(client, outbox)
    monkeypatch.setattr(
        api_connector,
        "fetch_external_api",
        lambda **kwargs: {"columns": [], "rows": [], "total_rows": 0, "suggestions": {}},
    )
    for _ in range(20):
        assert (
            client.post(
                "/api/crm/sources/preview/api", json={"url": "https://example.com/data"}
            ).status_code
            == 200
        )
    assert (
        client.post(
            "/api/crm/sources/preview/api", json={"url": "https://example.com/data"}
        ).status_code
        == 429
    )
    assert client.get("/api/crm/hub/status").status_code == 404
    assert client.post(f"/api/crm/sources/{uuid.uuid4()}/query", json={}).status_code == 404
    assert "refresh_interval_minutes" not in client.get("/api/crm/sources").json()[0]


def test_pdf_uses_receipt_engine_with_pixel_cap(monkeypatch):
    seen = []
    page = SimpleNamespace(
        rect=SimpleNamespace(width=100000, height=100000),
        get_pixmap=lambda **kwargs: (
            seen.append(kwargs["matrix"]),
            SimpleNamespace(tobytes=lambda kind: b"png"),
        )[1],
    )
    monkeypatch.setattr(
        pdf_reader.receipt_ocr,
        "extract",
        lambda raw: SimpleNamespace(texto_extraido="Cliente: Ana"),
    )
    assert pdf_reader._ocr_page(page) == "Cliente: Ana"
    scale = seen[0].a
    assert math.ceil(100000 * scale) ** 2 <= pdf_reader.MAX_PAGE_PIXELS


def test_migration_0039_upgrade_downgrade_preserves_source():
    path = (
        Path(__file__).parents[1]
        / "alembic/versions/20261120_0039_v1101_crm_sem_atualizacao_automatica.py"
    )
    spec = importlib.util.spec_from_file_location("crm_migration_0039", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    metadata = MetaData()
    table = Table(
        "data_sources",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("refresh_interval_minutes", Integer),
        Column("sync_failures", SmallInteger, nullable=False),
    )
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(table.insert().values(id=7, refresh_interval_minutes=5, sync_failures=2))
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
            assert {col["name"] for col in inspect(conn).get_columns("data_sources")} == {"id"}
            assert conn.exec_driver_sql("SELECT id FROM data_sources").scalar() == 7
            migration.downgrade()
            assert {col["name"] for col in inspect(conn).get_columns("data_sources")} == {
                "id",
                "refresh_interval_minutes",
                "sync_failures",
            }
            assert conn.exec_driver_sql("SELECT sync_failures FROM data_sources").scalar() == 0
    engine.dispose()


def test_crm_pdf_ocr_cap_rate_limit_cell_truncate_and_quota(
    client, db, outbox, tmp_path, monkeypatch
):
    from fpdf import FPDF
    from PIL import Image, ImageDraw

    _auth(client, outbox, "crm-limites@example.com")
    user = db.scalar(select(User).where(User.email == "crm-limites@example.com"))
    assert user is not None

    # C1: PDF escaneado com 7 páginas lê no máximo MAX_OCR_PAGES=5 e retorna aviso.
    img = Image.new("RGB", (400, 120), "white")
    ImageDraw.Draw(img).text((20, 20), "Cliente: Maria", fill="black")
    img_path = tmp_path / "p.png"
    img.save(img_path)
    pdf = FPDF()
    for _ in range(7):
        pdf.add_page()
        pdf.image(str(img_path), x=10, y=10, w=150)
    raw_pdf = bytes(pdf.output())

    ocr_calls = 0

    def fake_ocr(_page):
        nonlocal ocr_calls
        ocr_calls += 1
        return "Cliente: Maria\nValor: R$ 100,00"

    monkeypatch.setattr(pdf_reader, "_ocr_page", fake_ocr)
    extracted = pdf_reader.extract_pdf(raw_pdf, "7pags.pdf")
    assert ocr_calls == 5
    assert extracted.ocr_pages == 5
    assert extracted.warning == "Leia até 5 páginas digitalizadas por vez."

    # C1: limite de 5 chamadas por minuto em preview_csv / preview_pdf -> 6ª retorna 429.
    for _ in range(5):
        r = client.post(
            "/api/crm/sources/preview/csv",
            files={"file": ("ok.csv", b"Nome;Valor\nAna;10\n", "text/csv")},
        )
        assert r.status_code == 200
    rate_limited = client.post(
        "/api/crm/sources/preview/csv",
        files={"file": ("ok.csv", b"Nome;Valor\nAna;10\n", "text/csv")},
    )
    assert rate_limited.status_code == 429

    # C2: células de texto truncadas em 500 chars e limites no Pydantic (422).
    assert len(str(coerce_cell("a" * 750, "text"))) == 500
    too_many_cols = client.post(
        "/api/crm/sources/tabular",
        json={
            "name": "Wide",
            "kind": "csv",
            "columns": [{"name": f"c{i}", "label": f"C{i}", "type": "text"} for i in range(101)],
            "rows": [],
        },
    )
    assert too_many_cols.status_code == 422

    too_many_import = client.post(
        "/api/crm/sources/import-to-crm",
        json={"target": "contacts", "rows": [{"nome": "A"}] * 2001, "mapping": {"name": "nome"}},
    )
    assert too_many_import.status_code == 422

    # C2: snapshot do CRM respeita a cota de armazenamento (5 MB aqui).
    from app.models import StoredFile

    user.storage_quota_mb = 5
    db.add(
        StoredFile(
            owner_id=user.id,
            purpose="attachment",
            filename="quase-cheio.bin",
            content_type="application/octet-stream",
            size=5 * 1024 * 1024 - 10,
            width=0,
            height=0,
            data=b"x",
        )
    )
    db.commit()
    quota_err = client.post(
        "/api/crm/sources/tabular",
        json={
            "name": "Grande",
            "kind": "csv",
            "columns": [{"name": "nome", "label": "Nome", "type": "text"}],
            "rows": [{"nome": "Cliente com nome longo para passar de 10 bytes"}],
        },
    )
    assert quota_err.status_code == 413
    assert quota_err.json()["error"] == "quota_exceeded"


def test_crm_bridges_and_native_sources_respect_blocked_solutions(client, db, outbox):
    create_verified_user(client, outbox, "adm-crm-c4@example.com")
    adm = db.scalar(select(User).where(User.email == "adm-crm-c4@example.com"))
    assert adm is not None
    adm.is_admin = True
    db.commit()

    create_verified_user(client, outbox, "user-crm-c4@example.com")
    dono = db.scalar(select(User).where(User.email == "user-crm-c4@example.com"))
    assert dono is not None

    assert login(client, dono.email).status_code == 200
    sources_before = client.get("/api/crm/sources").json()
    budget_src = next(s for s in sources_before if s["kind"] == "native_budget")

    # Cria um negócio ganho para tentar sync-budget depois.
    board = client.get("/api/crm/pipeline").json()
    won_id = next(s for s in board["stages"] if s["is_won"])["id"]
    deal = client.post(
        "/api/crm/deals", json={"title": "Venda Bloqueio", "value": "500", "stage_id": won_id}
    ).json()

    assert login(client, adm.email).status_code == 200
    assert (
        client.patch(
            f"/api/admin/users/{dono.id}/permissions",
            json={"blocked_resources": ["meu-orcamento", "mensageria"], "storage_quota_mb": 50},
        ).status_code
        == 200
    )

    assert login(client, dono.email).status_code == 200
    visible_kinds = {s["kind"] for s in client.get("/api/crm/sources").json()}
    assert "native_budget" not in visible_kinds
    assert "native_messaging" not in visible_kinds
    assert client.get(f"/api/crm/sources/{budget_src['id']}/rows").status_code == 403
    assert client.post(f"/api/crm/deals/{deal['id']}/sync-budget").status_code == 403
    assert client.get("/api/crm/hub/messaging-chats").status_code == 403


def test_snapshot_size_bytes_stored_and_admin_storage_avoids_rows_json(client, db, engine, outbox):
    import json

    from sqlalchemy import event

    from app.models import DataSnapshot, DataSource
    from app.services import admin as admin_service

    _auth(client, outbox, "crm-r13@example.com")
    user = db.scalar(select(User).where(User.email == "crm-r13@example.com"))
    assert user is not None

    rows = [
        {"cliente": "João Café", "valor": 150.5},
        {"cliente": "Maria Ação", "valor": 299.9},
    ]
    res = client.post(
        "/api/crm/sources/tabular",
        json={
            "name": "Planilha R13",
            "kind": "csv",
            "columns": [
                {"name": "cliente", "label": "Cliente", "type": "text"},
                {"name": "valor", "label": "Valor", "type": "currency"},
            ],
            "rows": rows,
        },
    )
    assert res.status_code == 201, res.text
    source_id = uuid.UUID(res.json()["source"]["id"])
    snap = db.scalar(select(DataSnapshot).where(DataSnapshot.source_id == source_id))
    assert snap is not None
    raw_json = json.dumps(snap.rows_json, ensure_ascii=False, default=str)
    expected_bytes = len(raw_json.encode("utf-8"))
    assert snap.size_bytes == expected_bytes
    assert snap.size_bytes > 0

    seen_sql: list[str] = []

    def _capture(_conn, _cursor, statement: str, *_args):
        if statement.lstrip().upper().startswith("SELECT"):
            seen_sql.append(statement)

    event.listen(engine, "before_cursor_execute", _capture)
    try:
        assert admin_service.user_storage_bytes(db, user.id) == expected_bytes
        assert admin_service.user_storage_map(db)[user.id] == expected_bytes
    finally:
        event.remove(engine, "before_cursor_execute", _capture)

    assert seen_sql
    assert all("rows_json" not in stmt.lower() for stmt in seen_sql)
    assert any(s["kind"] == "csv" for s in client.get("/api/crm/sources").json())
    assert db.scalar(select(DataSource.id).where(DataSource.id == source_id)) == source_id
