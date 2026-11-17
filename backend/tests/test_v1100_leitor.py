"""v1.10.0: leitura de comprovante pelo leitor de cupons (RapidOCR) no lugar do Tesseract."""

import io
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from leitor_comprovantes import LeitorComprovantes
from PIL import Image, ImageDraw, ImageFont

from app.core.email import OutgoingEmail
from app.services import ocr
from tests.conftest import create_verified_user, login
from tests.test_v13 import CUPOM
from tests.test_v15 import NFCE
from tests.test_v1901_comprovante import BOLETO, REDE_MOLEZA

TODAY = date(2026, 11, 15)


def leitura(texto: str):
    """Resultado do leitor sobre um texto já lido (roda só o parser, sem carregar o OCR)."""
    return LeitorComprovantes().ler_texto(texto)


@pytest.fixture
def user(client: TestClient, outbox: list[OutgoingEmail]) -> TestClient:
    create_verified_user(client, outbox)
    login(client)
    return client


def test_cupom_pelo_leitor_mantem_total_data_e_loja() -> None:
    r = ocr.from_result(leitura(CUPOM), today=date(2026, 10, 21))
    assert (r.kind, r.amount, r.date) == ("cupom", Decimal("44.88"), date(2026, 10, 20))
    assert r.description == "Supermercado Bom Preco Ltda"
    assert r.payment_method == "cash"


def test_nfce_pelo_leitor_lista_cada_produto() -> None:
    r = ocr.from_result(leitura(NFCE), today=date(2026, 10, 21))
    assert r.amount == Decimal("43.39")
    assert [(i.description, i.amount) for i in r.items] == [
        ("Arroz Tipo 1 5Kg", Decimal("27.90")),
        ("Pastel De Queijo", Decimal("13.00")),
        ("Detergente Limpol 500Ml", Decimal("3.49")),
    ]


def test_cupom_real_pelo_leitor() -> None:
    # O mesmo cupom da v1.9.0.1: vale o "a pagar" (270,00), não o total antes do desconto.
    r = ocr.from_result(leitura(REDE_MOLEZA), today=TODAY)
    assert (r.kind, r.amount, r.date) == ("cupom", Decimal("270.00"), date(2024, 5, 9))
    assert r.description == "Rede Moleza"
    assert r.payment_method == "cash"
    assert r.items == []  # produtos mal lidos: a soma não fecha, nada é sugerido


def test_valor_a_pagar_vence_valor_pago_com_troco() -> None:
    # Achado na revisão do PR 73: o leitor ficava com o "valor pago" (50,00, com troco).
    texto = (
        "LOJA X\nARROZ 5KG 27,90\nFEIJAO 1KG 16,98\nVALOR A PAGAR R$ 44,88\n"
        "Dinheiro 50,00\nVALOR PAGO R$ 50,00\nTroco R$ 5,12\n"
    )
    r = ocr.from_result(leitura(texto), today=TODAY)
    assert r.amount == Decimal("44.88")
    assert [i.amount for i in r.items] == [Decimal("27.90"), Decimal("16.98")]


def test_produtos_nao_aparecem_com_total_que_nao_fecha() -> None:
    # Sem a linha de total e com o leitor reprovado, nenhum total fecha com os produtos.
    vazio = leitura(CUPOM).model_copy(update={"itens": []})
    texto_sem_total = CUPOM.replace("VALOR TOTAL R$                      44,88\n", "")
    vazio = vazio.model_copy(
        update={"texto_extraido": texto_sem_total, "valor_total": Decimal("99.00")}
    )
    vazio.validacao.aprovado = False
    r = ocr.from_result(vazio, today=date(2026, 10, 21))
    assert r.items == []


def test_boleto_continua_valendo() -> None:
    r = ocr.from_result(leitura(f"Banco\nLinha digitável\n{BOLETO}\n"), today=date(2025, 10, 1))
    assert (r.kind, r.amount, r.date) == ("boleto", Decimal("1234.56"), date(2025, 10, 25))
    assert r.payment_method == "boleto"


def test_um_produto_so_nao_vira_lista() -> None:
    texto = "PADARIA\nPAO FRANCES 0,512 KG 9,20\nTOTAL 9,20\n"
    assert ocr.from_result(leitura(texto), today=TODAY).items == []


def test_o_que_o_leitor_nao_acha_vem_das_regras_de_texto() -> None:
    vazio = leitura(CUPOM).model_copy(
        update={"valor_total": None, "data_hora": None, "estabelecimento": None, "itens": []}
    )
    r = ocr.from_result(vazio, today=date(2026, 10, 21))
    assert (r.amount, r.date) == (Decimal("44.88"), date(2026, 10, 20))
    assert r.description == "Supermercado Bom Preco Ltda"
    assert [i.amount for i in r.items] == [Decimal("27.90"), Decimal("16.98")]


def test_erro_do_leitor_vira_422(user: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    class Quebrado:
        def ler(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError("falha interna do OpenCV")

    monkeypatch.setattr(ocr, "_leitor", lambda: Quebrado())
    from tests.test_v075 import png  # noqa: PLC0415

    out = user.post("/api/receipts/read", files={"image": ("cupom.png", png(), "image/png")})
    assert out.status_code == 422 and out.json()["error"] == "ocr_failed"


def _foto_de_cupom() -> bytes:
    linhas = [
        "SUPERMERCADO BOM PRECO LTDA",
        "CNPJ 12.345.678/0001-90",
        "ARROZ 5KG   1 UN X 27,90   27,90",
        "FEIJAO 1KG  2 UN X 8,49    16,98",
        "VALOR TOTAL R$             44,88",
        "20/10/2026 18:42:10",
    ]
    fonte = ImageFont.load_default(size=28)
    image = Image.new("RGB", (760, 60 + 48 * len(linhas)), "white")
    desenho = ImageDraw.Draw(image)
    for n, linha in enumerate(linhas):
        desenho.text((30, 30 + 48 * n), linha, fill="black", font=fonte)
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def test_foto_de_cupom_de_ponta_a_ponta() -> None:
    """OCR de verdade (modelos do RapidOCR) sobre uma foto gerada."""
    r = ocr.read(_foto_de_cupom())
    assert r.kind == "cupom"
    assert r.amount == Decimal("44.88")
    assert r.date == date(2026, 10, 20)
