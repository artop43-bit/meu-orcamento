"""v1.5: vale-transporte e produtos do cupom."""

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.services import budget as budget_service
from app.services import ocr
from tests.conftest import create_verified_user, login
from tests.test_budget import Outbox, category_id, month

MONTH = "2030-01"


@pytest.fixture
def user(client: TestClient, outbox: Outbox) -> TestClient:
    create_verified_user(client, outbox)
    login(client)
    return client


@pytest.fixture(autouse=True)
def fixed_current_month(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(budget_service, "current_month", lambda *_: date(2030, 1, 1))


# ---------------------------------------------------------------- vale-transporte


def test_transport_voucher_pays_only_transport(user: TestClient) -> None:
    transport = category_id(user, "Transporte")
    out = user.post(
        "/api/accounts",
        json={"name": "VT", "kind": "transport", "benefit_amount": "220.00", "benefit_day": 1},
    )
    assert out.status_code == 201, out.text
    account = out.json()
    assert (account["kind"], account["benefit_category_id"]) == ("transport", transport)
    [recharge] = [i for i in month(user)["incomes"] if i["account_id"] == account["id"]]
    assert (recharge["description"], recharge["amount"]) == ("Recarga: VT", "220.00")
    wrong = user.post(
        f"/api/months/{MONTH}/expenses",
        json={
            "description": "Mercado",
            "amount": "40.00",
            "account_id": account["id"],
            "category_id": category_id(user, "Alimentação"),
        },
    )
    assert wrong.status_code == 400 and "só paga despesas de Transporte" in wrong.json()["message"]
    ok = user.post(
        f"/api/months/{MONTH}/expenses",
        json={
            "description": "Ônibus",
            "amount": "5.00",
            "account_id": account["id"],
            "category_id": transport,
        },
    )
    assert ok.status_code == 201, ok.text


# ---------------------------------------------------------------- produtos do cupom

NFCE = """MERCADO CENTRAL LTDA
CNPJ 12.345.678/0001-90
AV. BRASIL, 1500 - CENTRO
DOCUMENTO AUXILIAR DA NOTA FISCAL DE CONSUMIDOR ELETRONICA
# CODIGO DESCRICAO QTD UN VL UNIT VL TOTAL
001 7891234567890 ARROZ TIPO 1 5KG 1 UN X 27,90 27,90
002 7890000000001 PASTEL DE QUEIJO 2 UN X 6,50 13,00
003 7890000000002 DETERGENTE LIMPOL 500ML 1 UN X 3,49 3,49
DESCONTO -1,00
QTD. TOTAL DE ITENS 4
VALOR TOTAL R$ 43,39
CARTAO DE CREDITO 43,39
20/10/2026 18:42:10
"""


def test_receipt_lists_each_product() -> None:
    reading = ocr.parse(NFCE, today=date(2026, 10, 21))
    assert reading.amount == Decimal("43.39")
    assert [(i.description, i.amount) for i in reading.items] == [
        ("Arroz Tipo 1 5Kg", Decimal("27.90")),
        ("Pastel De Queijo", Decimal("13.00")),
        ("Detergente Limpol 500Ml", Decimal("3.49")),
    ]


def test_single_product_is_not_a_list() -> None:
    text = "PADARIA\nPAO FRANCES 0,512 KG 9,20\nTOTAL 9,20\n"
    assert ocr.parse(text, today=date(2026, 10, 21)).items == []


def test_read_receipt_suggests_category_per_item(
    user: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ocr, "read_text", lambda raw: NFCE)
    from tests.test_v075 import png  # noqa: PLC0415

    out = user.post("/api/receipts/read", files={"image": ("cupom.png", png(), "image/png")})
    assert out.status_code == 200, out.text
    items = out.json()["items"]
    assert len(items) == 3
    assert items[0]["category_id"] == category_id(user, "Alimentação")
