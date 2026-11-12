"""v1.7.6.1: exportação em PDF — o recorte escolhido e o resumo anual, como arquivo PDF."""

import io
import re

from fastapi.testclient import TestClient
from pypdf import PdfReader

from tests.test_data import MONTH, seed_month, user  # noqa: F401  (fixture)


def text_of(content: bytes) -> tuple[int, str]:
    reader = PdfReader(io.BytesIO(content))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    return len(reader.pages), re.sub(r"[ \t]+", " ", text)


def test_pdf_of_the_selection(user: TestClient) -> None:  # noqa: F811
    seed_month(user)
    response = user.get(f"/api/export/transactions?start={MONTH}&end=2030-02&format=pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert (
        'filename="meu-orcamento_2030-01_a_2030-02.pdf"' in response.headers["content-disposition"]
    )
    assert response.content.startswith(b"%PDF")
    pages, text = text_of(response.content)
    assert pages == 1
    # Cabeçalho, recorte aplicado e resumo.
    assert "Lançamentos" in text and "Janeiro de 2030 a fevereiro de 2030" in text
    assert "Receitas e despesas" in text and "Todos" in text and "Todas" in text
    assert "R$ 3.000,00" in text  # receitas
    assert "R$ 1.434,50" in text  # despesas: 1.234,50 + 2 × 100
    assert "R$ 1.565,50" in text  # saldo
    # Categorias, mês a mês e a lista, com acentos e "R$" certos.
    assert "Despesas por categoria" in text and "Moradia" in text and "Sem categoria" in text
    assert "Mês a mês" in text and "Fevereiro de 2030" in text
    assert "Aluguel; centro" in text and "-R$ 1.234,50" in text and "10/01/2030" in text
    assert "Celular (1/2)" in text and "Celular (2/2)" in text
    assert "Salário" in text
    assert "Página 1 de 1" in text


def test_pdf_respects_the_filters(user: TestClient) -> None:  # noqa: F811
    seed_month(user)
    moradia = next(c["id"] for c in user.get("/api/categories").json() if c["name"] == "Moradia")
    only = user.get(
        f"/api/export/transactions?start={MONTH}&end={MONTH}&format=pdf&kind=expense&category={moradia}"
    )
    _, text = text_of(only.content)
    assert "Só despesas" in text and "Categorias Moradia" in text
    assert "Aluguel; centro" in text
    assert "Celular" not in text and "Salário" not in text
    assert "Mês a mês" not in text  # um mês só
    incomes = user.get(f"/api/export/transactions?start={MONTH}&end={MONTH}&format=pdf&kind=income")
    _, text = text_of(incomes.content)
    assert "Só receitas" in text and "Salário" in text and "Aluguel" not in text
    assert "Despesas por categoria" not in text and "Categorias" not in text


def test_pdf_of_an_empty_selection_and_long_periods(user: TestClient) -> None:  # noqa: F811
    empty = user.get("/api/export/transactions?start=2031-01&end=2031-01&format=pdf")
    assert empty.status_code == 200
    _, text = text_of(empty.content)
    assert "Nenhum lançamento neste recorte" in text
    # Muitos lançamentos: várias páginas, com o cabeçalho da tabela repetido.
    for index in range(70):
        user.post(
            f"/api/months/{MONTH}/expenses",
            json={"description": f"Café da manhã nº {index}", "amount": "12.30"},
        )
    long = user.get(f"/api/export/transactions?start={MONTH}&end={MONTH}&format=pdf")
    pages, text = text_of(long.content)
    assert pages >= 2
    assert f"Página {pages} de {pages}" in text
    assert text.count("Descrição") >= pages  # cabeçalho da tabela em cada página
    assert "Café da manhã nº 69" in text


def test_annual_pdf(user: TestClient) -> None:  # noqa: F811
    seed_month(user)
    response = user.get("/api/export/annual.pdf?year=2030")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "meu-orcamento_resumo-anual_2030.pdf" in response.headers["content-disposition"]
    _, text = text_of(response.content)
    assert "Resumo anual" in text and "2030" in text
    assert "Taxa de poupança" in text
    assert "Para o Imposto de Renda" in text and "não é documento fiscal" in text
    assert "Rendimentos fixos" in text
    assert "Janeiro de 2030" in text
    assert user.get("/api/export/annual.pdf?year=1990").status_code == 422


def test_pdf_needs_login(client: TestClient) -> None:
    assert client.get(f"/api/export/transactions?start={MONTH}&format=pdf").status_code == 401
    assert client.get("/api/export/annual.pdf?year=2030").status_code == 401
