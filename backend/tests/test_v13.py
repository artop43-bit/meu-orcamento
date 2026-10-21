"""v1.3: compra dividida em categorias, lançamento feito sem internet e leitura de comprovante."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.services import budget as budget_service
from app.services import ocr
from tests.conftest import create_verified_user, login
from tests.test_budget import Outbox, add_expense, category_id, month

MONTH = "2030-01"


@pytest.fixture
def user(client: TestClient, outbox: Outbox) -> TestClient:
    create_verified_user(client, outbox)
    login(client)
    return client


@pytest.fixture(autouse=True)
def fixed_current_month(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(budget_service, "current_month", lambda *_: date(2030, 1, 1))


# ---------------------------------------------------------------- dividir em categorias


def test_split_purchase_creates_one_expense_per_category(user: TestClient) -> None:
    food, health = category_id(user, "Alimentação"), category_id(user, "Saúde")
    parts = [{"category_id": food, "amount": "150.00"}, {"category_id": health, "amount": "40.00"}]
    created = add_expense(user, description="Supermercado", amount="190.00", parts=parts)
    assert [(e["category_id"], e["amount"]) for e in created] == [
        (food, "150.00"),
        (health, "40.00"),
    ]
    group = created[0]["split_group_id"]
    assert group and created[1]["split_group_id"] == group
    # Nada em dobro: o total do mês é a compra, uma vez só.
    data = month(user)
    assert Decimal(data["summary"]["expense_total"]) == Decimal("190.00")
    # Pagar uma parte paga a compra inteira.
    out = user.patch(f"/api/expenses/{created[0]['id']}", json={"paid": True})
    assert out.status_code == 200
    assert all(e["paid"] for e in month(user)["expenses"] if e["split_group_id"] == group)


def test_split_parts_must_add_up_to_the_total(user: TestClient) -> None:
    food = category_id(user, "Alimentação")
    parts = [{"category_id": food, "amount": "100.00"}, {"category_id": food, "amount": "50.00"}]
    out = user.post(
        f"/api/months/{MONTH}/expenses",
        json={"description": "X", "amount": "190.00", "parts": parts},
    )
    assert out.status_code == 400
    assert "R$ 150,00" in out.json()["message"] and "R$ 190,00" in out.json()["message"]
    # Divisão não combina com parcelas.
    parts[1]["amount"] = "90.00"
    out = user.post(
        f"/api/months/{MONTH}/expenses",
        json={"description": "X", "amount": "190.00", "parts": parts, "installments": 3},
    )
    assert out.status_code == 400 and out.json()["error"] == "split_single"


# ---------------------------------------------------------------- sem internet


def test_offline_expense_sent_twice_is_created_once(user: TestClient) -> None:
    ref = str(uuid.uuid4())
    first = add_expense(user, description="Padaria", amount="12.50", client_ref=ref)
    again = add_expense(user, description="Padaria", amount="12.50", client_ref=ref)
    assert [e["id"] for e in again] == [e["id"] for e in first]
    assert [e["description"] for e in month(user)["expenses"]].count("Padaria") == 1


def test_offline_income_sent_twice_is_created_once(user: TestClient) -> None:
    ref = str(uuid.uuid4())
    payload = {"description": "Freela", "amount": "300.00", "client_ref": ref}
    first = user.post(f"/api/months/{MONTH}/incomes", json=payload)
    again = user.post(f"/api/months/{MONTH}/incomes", json=payload)
    assert first.status_code == again.status_code == 201
    assert first.json()["id"] == again.json()["id"]
    assert len(month(user)["incomes"]) == 1


# ---------------------------------------------------------------- comprovante por foto


CUPOM = """SUPERMERCADO BOM PRECO LTDA
CNPJ 12.345.678/0001-90
RUA DAS FLORES, 100
CUPOM FISCAL ELETRONICO - SAT
ARROZ 5KG            1 UN X 27,90   27,90
FEIJAO 1KG           2 UN X 8,49    16,98
QTD. TOTAL DE ITENS 3
VALOR TOTAL R$                      44,88
DINHEIRO                            50,00
TROCO R$                             5,12
20/10/2026 18:42:10
"""


def test_receipt_text_finds_total_date_and_store() -> None:
    reading = ocr.parse(CUPOM, today=date(2026, 10, 21))
    assert reading.kind == "cupom"
    assert reading.amount == Decimal("44.88")
    assert reading.date == date(2026, 10, 20)
    assert reading.description == "Supermercado Bom Preco Ltda"


def test_boleto_line_gives_exact_amount_and_due_date() -> None:
    # Fator 1000 (nova base, 22/02/2025) + 245 dias = 25/10/2025; valor R$ 1.234,56.
    line = "23790.12345 60000.123456 78901.234567 8 12450000123456"
    reading = ocr.parse(f"Banco\nLinha digitável\n{line}\n", today=date(2025, 10, 1))
    assert reading.kind == "boleto"
    assert reading.amount == Decimal("1234.56")
    assert reading.date == date(2025, 10, 25)


def test_read_receipt_endpoint(user: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ocr, "read_text", lambda raw: CUPOM)
    from tests.test_v075 import png  # noqa: PLC0415

    out = user.post("/api/receipts/read", files={"image": ("cupom.png", png(), "image/png")})
    assert out.status_code == 200, out.text
    assert out.json()["amount"] == "44.88" and out.json()["kind"] == "cupom"


def test_read_receipt_without_ocr_explains(
    user: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ocr, "available", lambda: False)
    from tests.test_v075 import png  # noqa: PLC0415

    out = user.post("/api/receipts/read", files={"image": ("cupom.png", png(), "image/png")})
    assert out.status_code == 503 and "não está disponível" in out.json()["message"]


# ---------------------------------------------------------------- sobra do limite (v1.3 B)


def test_unused_limit_carries_to_next_month_when_enabled(
    user: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    lazer = category_id(user, "Lazer")
    out = user.patch(
        f"/api/categories/{lazer}", json={"monthly_limit": "300.00", "carry_over": True}
    )
    assert out.status_code == 200 and out.json()["carry_over"] is True
    assert out.json()["carry_since"] == "2030-01-01"
    add_expense(user, description="Cinema", amount="80.00", category_id=lazer)
    # Fevereiro começa com 300 + 220 que sobraram de janeiro.
    add_expense(user, month="2030-02", description="Show", amount="100.00", category_id=lazer)
    [row] = [
        c for c in month(user, "2030-02")["summary"]["by_category"] if c["category_id"] == lazer
    ]
    assert (row["limit"], row["limit_carried"]) == ("520.00", "220.00")
    # Estourar não tira do mês seguinte: março volta a ter só o acumulado positivo.
    add_expense(user, month="2030-02", description="Viagem", amount="600.00", category_id=lazer)
    add_expense(user, month="2030-03", description="Bar", amount="10.00", category_id=lazer)
    [row] = [
        c for c in month(user, "2030-03")["summary"]["by_category"] if c["category_id"] == lazer
    ]
    assert (row["limit"], row["limit_carried"]) == ("300.00", None)
    # Desligar volta ao limite simples.
    user.patch(f"/api/categories/{lazer}", json={"carry_over": False})
    [row] = [
        c for c in month(user, "2030-02")["summary"]["by_category"] if c["category_id"] == lazer
    ]
    assert row["limit"] == "300.00"


def test_limit_without_carry_over_stays_the_same(user: TestClient) -> None:
    lazer = category_id(user, "Lazer")
    user.patch(f"/api/categories/{lazer}", json={"monthly_limit": "300.00"})
    add_expense(user, description="Cinema", amount="80.00", category_id=lazer)
    add_expense(user, month="2030-02", description="Show", amount="100.00", category_id=lazer)
    [row] = [
        c for c in month(user, "2030-02")["summary"]["by_category"] if c["category_id"] == lazer
    ]
    assert (row["limit"], row["limit_carried"]) == ("300.00", None)


# ---------------------------------------------------------------- inflação (v1.3 B)


def test_inflation_correction_uses_months_after_the_start(
    user: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import indicators

    series = {"2024-01": 0.42, "2024-02": 0.83, "2024-03": 0.16, "2024-04": 0.38}
    monkeypatch.setattr(indicators, "ipca_monthly", lambda: series)
    out = user.get("/api/indicators/inflation?amount=100&start=2024-01&end=2030-01")
    assert out.status_code == 200, out.text
    data = out.json()
    # Fevereiro a abril: 1,0083 × 1,0016 × 1,0038 = 1,01375...
    assert data["corrected"] == 101.38 and data["months"] == 3 and data["end"] == "2024-04"
    bad = user.get("/api/indicators/inflation?amount=100&start=2024-04&end=2024-02")
    assert bad.status_code == 400


def test_inflation_without_bcb_explains(user: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import indicators

    monkeypatch.setattr(indicators, "ipca_monthly", lambda: {})
    out = user.get("/api/indicators/inflation?amount=100&start=2020-01&end=2024-01")
    assert out.status_code == 503 and "Banco Central" in out.json()["message"]


# ---------------------------------------------------------------- desafios (v1.3 C)


@pytest.fixture
def jan10(monkeypatch: pytest.MonkeyPatch) -> date:
    from app.services import challenges

    today = date(2030, 1, 10)
    monkeypatch.setattr(challenges, "today_local", lambda: today)
    return today


def test_delivery_challenge_is_lost_by_an_ifood_order(user: TestClient, jan10: date) -> None:
    out = user.post("/api/challenges", json={"template": "delivery"})
    assert out.status_code == 201, out.text
    challenge = out.json()
    assert (challenge["status"], challenge["days"], challenge["end_date"]) == (
        "active",
        30,
        "2030-02-08",
    )
    add_expense(user, description="Mercado", amount="80.00", due_date="2030-01-10")
    assert user.get("/api/challenges").json()[0]["status"] == "active"
    add_expense(user, description="IFOOD *Pizzaria", amount="45.00", due_date="2030-01-10")
    [row] = user.get("/api/challenges").json()
    assert row["status"] == "lost" and row["slips"][0]["description"] == "IFOOD *Pizzaria"


def test_category_ceiling_challenge(user: TestClient, jan10: date) -> None:
    lazer = category_id(user, "Lazer")
    out = user.post(
        "/api/challenges",
        json={"template": "leisure", "max_amount": "200.00", "category_id": lazer},
    )
    assert out.status_code == 201, out.text
    add_expense(
        user, description="Cinema", amount="150.00", category_id=lazer, due_date="2030-01-10"
    )
    [row] = user.get("/api/challenges").json()
    assert (row["status"], row["spent"]) == ("active", "150.00")
    add_expense(user, description="Show", amount="60.00", category_id=lazer, due_date="2030-01-10")
    assert user.get("/api/challenges").json()[0]["status"] == "lost"


def test_challenge_is_won_when_the_period_ends_clean(
    user: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import challenges

    monkeypatch.setattr(challenges, "today_local", lambda: date(2030, 1, 1))
    user.post("/api/challenges", json={"template": "essentials"})
    monkeypatch.setattr(challenges, "today_local", lambda: date(2030, 1, 9))
    [row] = user.get("/api/challenges").json()
    assert row["status"] == "won" and row["elapsed_days"] == 7
    # Desafio personalizado sem as informações necessárias explica o que falta.
    bad = user.post("/api/challenges", json={"title": "Sem bar", "kind": "no_keyword", "days": 7})
    assert bad.status_code == 400 and "palavras" in bad.json()["message"]


# ---------------------------------------------------------------- modo sem culpa (v1.3 C)


def test_recovery_plan_for_a_negative_month(user: TestClient) -> None:
    lazer = category_id(user, "Lazer")
    user.post(f"/api/months/{MONTH}/incomes", json={"description": "Salário", "amount": "1000.00"})
    add_expense(
        user, description="Aluguel", amount="900.00", category_id=category_id(user, "Moradia")
    )
    add_expense(user, description="Viagem", amount="400.00", category_id=lazer)
    add_expense(user, month="2029-12", description="Cinema", amount="90.00", category_id=lazer)
    plan = user.get(f"/api/months/{MONTH}/recovery").json()
    assert plan["deficit"] == "300.00"
    assert [(s["months"], s["per_month"]) for s in plan["spread"]] == [
        (1, "300.00"),
        (3, "100.00"),
        (6, "50.00"),
    ]
    # Lazer passou da média (90 / 3 = 30); Moradia é essencial e fica de fora.
    assert plan["cuts"][0]["name"] == "Lazer" and plan["cuts"][0]["above_average"] == "370.00"
    assert all(c["name"] != "Moradia" for c in plan["cuts"])
    # Mês positivo: nada a planejar.
    assert user.get("/api/months/2030-03/recovery").json()["deficit"] == "0"


# ---------------------------------------------------------------- resumo semanal (v1.3 C)


def test_weekly_summary_on_monday(user: TestClient, db, outbox: Outbox) -> None:  # type: ignore[no-untyped-def]
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from app.services import notify

    monday = date(2030, 1, 14)
    add_expense(user, description="Mercado", amount="150.00", due_date="2030-01-09", paid=True)
    add_expense(user, description="Internet", amount="99.90", due_date="2030-01-16")
    outbox.clear()
    at = datetime(2030, 1, 14, 8, 30, tzinfo=ZoneInfo("America/Sao_Paulo"))
    assert monday.weekday() == 0
    assert notify.run_daily(db, at)["weekly"] == 1
    [mail] = [m for m in outbox if "semana" in m.subject]
    assert "R$ 150,00" in mail.body and "Internet" in mail.body
    assert notify.run_daily(db, at)["weekly"] == 0  # não repete
    # Desligar pelo app.
    prefs = user.patch("/api/notifications/prefs", json={"notify_weekly": False}).json()
    assert prefs["notify_weekly"] is False


# ---------------------------------------------------------------- painel do Orçamento (v1.3 D)


def test_dashboard_order_is_saved_on_the_account(user: TestClient) -> None:
    import json

    assert user.get("/api/auth/me").json()["dashboard"] is None
    cards = [
        {"key": "daily", "visible": True},
        {"key": "kpis", "visible": False},
        {"key": "daily", "visible": False},
    ]
    out = user.put("/api/me/dashboard", json={"cards": cards})
    assert out.status_code == 200
    saved = json.loads(user.get("/api/auth/me").json()["dashboard"])
    assert saved == [{"key": "daily", "visible": True}, {"key": "kpis", "visible": False}]
    assert (
        user.put(
            "/api/me/dashboard", json={"cards": [{"key": "outro", "visible": True}]}
        ).status_code
        == 422
    )
    # Restaurar o padrão.
    user.put("/api/me/dashboard", json={"cards": None})
    assert user.get("/api/auth/me").json()["dashboard"] is None


# ---------------------------------------------------------------- painel de erros (v1.3 D)


def test_screen_errors_are_grouped_and_scrubbed(
    client: TestClient, outbox: Outbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "admin_emails", "chefe@example.com")
    error = {
        "name": "TypeError",
        "message": "Cannot read 'amount' of ana@example.com 1234,56 "
        "(id 0b1e0f0e-1111-4222-8333-944445555666)",
        "path": "/dividas/0b1e0f0e-1111-4222-8333-944445555666?x=1",
        "release": "1.3.0",
    }
    for _ in range(3):
        assert client.post("/api/errors", json=error).status_code == 204
    create_verified_user(client, outbox, "chefe@example.com")
    login(client, "chefe@example.com")
    [row] = client.get("/api/admin/errors").json()
    assert row["count"] == 3 and row["source"] == "web" and row["path"] == "/dividas/[id]"
    assert "ana@example.com" not in row["message"] and "1234" not in row["message"]
    assert "[e-mail]" in row["message"] and "[id]" in row["message"]
    assert client.post(f"/api/admin/errors/{row['id']}/resolve").status_code == 204
    assert client.get("/api/admin/errors").json()[0]["resolved_at"] is not None
    # Quem não é administrador não vê o painel.
    client.post("/api/auth/logout")
    create_verified_user(client, outbox, "ana@example.com")
    login(client)
    assert client.get("/api/admin/errors").status_code == 403


def test_unexpected_server_error_is_recorded(
    client: TestClient, outbox: Outbox, monkeypatch: pytest.MonkeyPatch, db
) -> None:  # type: ignore[no-untyped-def]
    from fastapi.testclient import TestClient as Client

    from app.models import ErrorEvent
    from app.services import budget as budget_service

    create_verified_user(client, outbox)
    login(client)

    def boom(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("falhou ao somar 987654 reais")

    monkeypatch.setattr(budget_service, "get_month", boom)
    quiet = Client(client.app, raise_server_exceptions=False, cookies=client.cookies)
    out = quiet.get(f"/api/months/{MONTH}")
    assert out.status_code == 500 and "registrado" in out.json()["message"]
    event = db.query(ErrorEvent).one()
    assert (event.source, event.name, event.path) == (
        "api",
        "RuntimeError",
        "GET /api/months/[data]",
    )
    assert "987654" not in event.message
