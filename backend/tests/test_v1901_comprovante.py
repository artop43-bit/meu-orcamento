"""v1.9.0.1: leitura de comprovante corrigida (cupom confundido com boleto, total e pagamento)."""

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.email import OutgoingEmail
from app.services import ocr
from tests.conftest import create_verified_user, login

# Texto que o Tesseract do servidor leu da foto do cupom enviado pelo usuário (15/11/2026),
# do jeito que saiu: sujeira das bordas, "279.17" com ponto e vírgulas perdidas nos produtos.
REDE_MOLEZA = """|
|
REDE MOLEZA
CNPJ: 88709 583/0001-02 | E: 0962841714
Fone. (51) 32822064 ae com br
AV ASSIS BRASIL. 2990 - CRISTO REDENTOR - Porto
Alegre - RS - CEP 91010002
| Documento Auxiliar da Nota Fiscal Eletronica de Consumidor
| Código Qtde UN VI Unit. VI. Total
| 3834 BOLAS COURO 2UN 1990 3980
] SINTETICO NS
BET Ta 959169 FILTRO LINHA 5 TOM 6 UN 35,90 21540
Pa 2P+T PTP
PRN fee 3xX0,75MM SAQ 1M
, epa 9591  PULVERIZADOR SUN 7,99 2397
eae rio GIRRAFA SOOML
Ses Quantidade Total de Itens 14
Doo Valor Total R$: 279.17
= = Desconto R$; 9,17
E = | Acróscimo R$. 0,00
sd Valor a Pagar R$; 270,00 .
ER de FORMA PAGAMENTO VALOR PAGO R$
pio ae? Dinheiro 270,00 |
E at Consulte pela Chave de Acesso em
Ee + https:/www .sefaz rs gov. br/NFCE/NFCE-COM aspx
ER 4324 0588 7095 6300 0102 6500 1000 2184 2540 0220 5730 |
eta à sr eNPJ: 44.699,448/0001-410 |
=== Deo Nor |
Sê Ee OS RiZINFC-o nº 218.435 |
qua: [=] tia ao Sério 1 09/05/2024 12:16:38
Protocolo autorização:
243240019184153
"""

# Linha digitável válida (dígitos verificadores certos): banco 237, fator 1245, R$ 1.234,56.
BOLETO = "23791.23454 67890.123457 67890.123457 3 12450000123456"
TODAY = date(2026, 11, 15)


def test_cupom_real_nao_vira_boleto() -> None:
    reading = ocr.parse(REDE_MOLEZA, today=TODAY)
    assert reading.kind == "cupom"
    assert reading.amount == Decimal("270.00")
    assert reading.date == date(2024, 5, 9)
    assert reading.description == "Rede Moleza"
    assert reading.payment_method == "cash"


def test_produtos_mal_lidos_nao_viram_lista() -> None:
    # Sem as vírgulas ("1990 3980") a soma não bate com o total: melhor não sugerir nada.
    assert ocr.parse(REDE_MOLEZA, today=TODAY).items == []


def test_boleto_valido() -> None:
    reading = ocr.parse(f"Banco\nLinha digitável\n{BOLETO}\n", today=date(2025, 10, 1))
    assert reading.kind == "boleto"
    assert reading.amount == Decimal("1234.56")
    assert reading.date == date(2025, 10, 25)
    assert reading.payment_method == "boleto"


def test_boleto_em_duas_linhas() -> None:
    first, second = BOLETO[:24], BOLETO[24:]
    reading = ocr.parse(f"Pagável em qualquer banco\n{first}\n{second}\n", today=date(2025, 10, 1))
    assert reading.kind == "boleto" and reading.amount == Decimal("1234.56")


@pytest.mark.parametrize(
    "line",
    [
        "23790.12345 60000.123456 78901.234567 8 12450000123456",  # dígitos verificadores errados
        BOLETO.replace("12450000123456", "12450000123457"),  # valor trocado (DV geral não bate)
    ],
)
def test_linha_com_digito_errado_nao_e_boleto(line: str) -> None:
    assert ocr.parse(f"Banco\nLinha digitável\n{line}\nTOTAL 10,00\n", today=TODAY).kind == "cupom"


def test_numeros_espalhados_nao_formam_boleto() -> None:
    text = (
        "FILTRO LINHA 1,00\nCNPJ 12345678000190\nFone 5133333333\n"
        "4324 0588 7095 6300 0102 6500 1000 2184 2540 0220 5730\nTOTAL 1,00\n"
    )
    assert ocr.parse(text, today=TODAY).kind == "cupom"


def test_valor_a_pagar_vence_valor_total() -> None:
    text = "LOJA X\nVALOR TOTAL R$ 100,00\nDESCONTO R$ 10,00\nVALOR A PAGAR R$ 90,00\n"
    assert ocr.parse(text, today=TODAY).amount == Decimal("90.00")


def test_total_com_ponto_do_ocr() -> None:
    assert ocr.parse("LOJA X\nTOTAL R$: 45.90\n", today=TODAY).amount == Decimal("45.90")


def test_linha_de_baixo_de_desconto_nao_e_total() -> None:
    text = "LOJA X\nVALOR TOTAL R$\nDESCONTO R$ 9,17\nDINHEIRO 50,00\n"
    assert ocr.parse(text, today=TODAY).amount != Decimal("9.17")


@pytest.mark.parametrize(
    ("line", "method"),
    [
        ("DINHEIRO 50,00", "cash"),
        ("CARTAO DE CREDITO 43,39", "credit"),
        ("CARTAO DEBITO 43,39", "debit"),
        ("PIX 43,39", "pix"),
        ("Forma de pagamento: Crédito à vista", "credit"),
    ],
)
def test_forma_de_pagamento(line: str, method: str) -> None:
    text = f"LOJA X\nARROZ 43,39\nVALOR TOTAL R$ 43,39\n{line}\n"
    assert ocr.parse(text, today=TODAY).payment_method == method


def test_pagamento_ambiguo_fica_em_branco() -> None:
    text = "LOJA X\nVALOR TOTAL R$ 50,00\nDINHEIRO 20,00\nPIX 30,00\n"
    assert ocr.parse(text, today=TODAY).payment_method is None


def test_produto_com_nome_de_pagamento_nao_conta() -> None:
    # "Débito" no meio dos produtos (antes do total) não é a forma de pagamento.
    text = "LOJA X\nCAPA CARTAO DEBITO 10,00\nPILHA 5,00\nTOTAL 15,00\n"
    assert ocr.parse(text, today=TODAY).payment_method is None


@pytest.fixture
def user(client: TestClient, outbox: list[OutgoingEmail]) -> TestClient:
    create_verified_user(client, outbox)
    login(client)
    return client


def test_endpoint_devolve_forma_de_pagamento(
    user: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ocr, "read_text", lambda raw: REDE_MOLEZA)
    from tests.test_v075 import png  # noqa: PLC0415

    out = user.post("/api/receipts/read", files={"image": ("cupom.png", png(), "image/png")})
    assert out.status_code == 200, out.text
    body = out.json()
    assert body["kind"] == "cupom" and body["amount"] == "270.00"
    assert body["payment_method"] == "cash"


# ---------------------------------------------------------------- resumo da semana e cartão


def test_resumo_da_semana_mostra_a_fatura_e_nao_a_compra(
    user: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Achado no CI de 16/11/2026 (uma segunda): a compra no cartão aparecia solta no resumo
    da semana, em vez da fatura (o lembrete de vencimentos já mostrava a fatura)."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from app.services import budget as budget_service
    from app.services import notify

    monkeypatch.setattr(budget_service, "current_month", lambda *_: date(2030, 1, 1))
    card = user.post(
        "/api/cards",
        json={"name": "Roxo", "kind": "credit", "closing_day": 1, "due_day": 16},
    ).json()
    user.post(
        "/api/months/2029-12/expenses",
        json={
            "description": "Tênis",
            "amount": "300.00",
            "card_id": card["id"],
            "purchase_date": "2029-12-10",
        },
    )
    from app.core.email import outbox
    from app.db.session import get_db
    from app.main import app

    db = next(app.dependency_overrides[get_db]())
    outbox.clear()
    monday = datetime(2030, 1, 14, 8, 30, tzinfo=ZoneInfo("America/Sao_Paulo"))
    assert monday.weekday() == 0
    notify.run_daily(db, monday)
    [weekly] = [m for m in outbox if "semana" in m.subject]
    assert "Tênis" not in weekly.body
    assert "Fatura Roxo" in weekly.body and "16/01" in weekly.body
