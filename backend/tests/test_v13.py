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
