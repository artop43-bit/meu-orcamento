import json

import pytest
from sqlalchemy import select

from app.models.user import User
from app.services import rtc
from tests.conftest import create_verified_user, login


@pytest.fixture
def sessao(client, outbox):
    create_verified_user(client, outbox)
    assert login(client).status_code == 200
    return client


@pytest.fixture(autouse=True)
def limpar_cache():
    rtc._dados_publicos.cache_clear()
    yield
    rtc._dados_publicos.cache_clear()


def test_rotas_fiscais_requerem_conta(client):
    assert client.get("/api/rtc/referencias/ncm?data=2026-11-20").status_code == 401
    assert client.post("/api/rtc/simular", json={}).status_code == 401
    assert client.post("/api/rtc/danfse", content=b"<NFSe/>").status_code == 401


def test_rotas_fiscais_respeitam_bloqueio_do_meu_orcamento(sessao, db):
    pessoa = db.scalar(select(User).where(User.email == "ana@example.com"))
    assert pessoa is not None
    pessoa.blocked_resources = '["meu-orcamento"]'
    db.commit()
    assert sessao.get("/api/rtc/referencias/ncm?data=2026-11-20").status_code == 403
    assert sessao.post("/api/rtc/danfse", content=b"<NFSe/>").status_code == 403


def test_simulacao_regular_parcial_preserva_codigos_e_valores(sessao, monkeypatch):
    def motor(nome, caminho, corpo):
        entrada = json.loads(corpo)
        assert nome == "regular"
        assert caminho.endswith("/regime-geral")
        assert entrada["municipio"] == 3550308
        assert entrada["itens"][0]["cClassTrib"] == "000001"
        assert entrada["itens"][0]["baseCalculo"] == "100.00"
        return (
            b"""{
              "objetos": [
                {"nObj": 1, "estadoItem": "CALCULO_SIMULADO", "tribCalc": {"IBSCBS": {
                  "memoriaCalculo": {"CBS": ["Memoria da CBS"]},
                  "gIBSCBS": {"vBC": 100.00, "gCBS": {"vCBS": 0.90, "pCBS": 0.9}}
                }}},
                {"nObj": 2, "estadoItem": "INCONSISTENCIA_ENTRADA",
                 "erros": [{"code": "T01", "detail": "Confira o CST"}]}
              ],
              "total": {"IBSCBSTot": {"vBCIBSCBS": 100.00, "gCBS": {"vCBS": 0.90}}}
            }""",
            {"X-CALC-APP-VERSION": "1.7.2", "X-CALC-DB-VERSION": "7"},
        )

    monkeypatch.setattr(rtc, "consulta_motor", motor)
    item = {"cst": "000", "classificacao": "000001", "base": "100.00"}
    resposta = sessao.post(
        "/api/rtc/simular",
        json={
            "regime": "regular",
            "data": "2027-03-15",
            "documento": "55",
            "uf": "SP",
            "municipio": 3550308,
            "itens": [item | {"cbs": "0.9"}, item],
        },
    )
    assert resposta.status_code == 200, resposta.text
    resultado = resposta.json()
    assert resultado["parcial"] and resultado["simulado"]
    assert resultado["versao_base"] == "7"
    assert resultado["totais"]["cbs"] == {"valor": "0.90", "base": "100.00"}
    assert resultado["itens"][0]["tributos"]["cbs"]["aliquota"] == "0.9"
    assert resultado["itens"][0]["memoria"] == ["Memoria da CBS"]
    assert resultado["itens"][1]["erros"] == ["T01 Confira o CST"]


def test_simples_usa_contrato_de_nfse(sessao, monkeypatch):
    def motor(nome, caminho, corpo):
        entrada = json.loads(corpo)
        assert nome == "simples"
        assert caminho.endswith("/simples-nacional/nao-assistido")
        assert entrada["versao"] == "3.0.0"
        assert entrada["aliquotasEfetivas"] == {
            "fatorR": False,
            "anexoIII": {"pCBSSN": "2.2154", "pIBSSN": "0.0257"},
        }
        assert entrada["itens"][0]["tribISSQN"] == "1"
        return (
            b"""{"objetos": [{"nObj": 1, "estadoItem": "CALCULADO", "tribCalc":
                {"vBC": 10000.00, "vCBSSN": 222.00, "vIBSSN": 3.00}}],
                "total": {"vCBSSNtot": 222.00, "vIBSSNtot": 3.00}}""",
            {},
        )

    monkeypatch.setattr(rtc, "consulta_motor", motor)
    item = {
        "atividade": "07",
        "classificacao": "000001",
        "base": "10000.00",
        "cbs": "2.2154",
        "ibs": "0.0257",
    }
    entrada = {
        "regime": "simples",
        "data": "2027-03-15",
        "documento": "91",
        "anexo": "III",
        "fator_r": False,
        "itens": [item],
    }
    assert (
        sessao.post("/api/rtc/simular", json=entrada | {"itens": [item, item]}).status_code == 422
    )
    resposta = sessao.post("/api/rtc/simular", json=entrada)
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["totais"]["ibs"]["valor"] == "3.00"
    assert resposta.json()["simulado"]
    assert not resposta.json()["parcial"]


def test_catalogo_busca_sem_acento_e_abre_norma(sessao, monkeypatch):
    def motor(nome, caminho):
        assert nome == "regular"
        assert "data=2026-11-20" in caminho
        if "fundamentacoes" in caminho:
            dado = [
                {
                    "codigoClassificacaoTributaria": "000001",
                    "textoCurto": "Art. 1",
                    "texto": "Texto fiscal de teste",
                }
            ]
        else:
            dado = [
                {
                    "codigo": "000",
                    "classificacoesTributarias": [
                        {"codigo": "000001", "descricao": "Tributação integral"},
                    ],
                }
            ]
        return json.dumps(dado).encode(), {"X-CALC-DB-VERSION": "7"}

    monkeypatch.setattr(rtc, "consulta_motor", motor)
    resultado = sessao.get(
        "/api/rtc/referencias/classificacao",
        params={"data": "2026-11-20", "q": "TRIBUTACAO 000001"},
    ).json()
    assert resultado["itens"] == [
        {"codigo": "000001", "descricao": "Tributação integral", "cst": "000"}
    ]
    assert resultado["versao_base"] == "7"
    assert sessao.get(
        "/api/rtc/fundamentos",
        params={"tipo": "classificacao", "codigo": "000001", "data": "2026-11-20"},
    ).json() == [{"referencia": "Art. 1", "texto": "Texto fiscal de teste"}]


def test_pdf_limita_xml_e_evita_cache(sessao, monkeypatch):
    def motor(nome, caminho, corpo, tipo):
        assert (nome, caminho, tipo) == ("danfse", "/api/danfse", "application/xml")
        assert corpo == b"<NFSe/>"
        return b"%PDF-1.4 teste", {}

    monkeypatch.setattr(rtc, "consulta_motor", motor)
    monkeypatch.setattr(rtc, "MAX_XML", 32)
    assert sessao.post("/api/rtc/danfse", content=b"<NFSe/>").status_code == 415
    headers = {"Content-Type": "application/xml"}
    assert sessao.post("/api/rtc/danfse", content=b" ", headers=headers).status_code == 422
    assert sessao.post("/api/rtc/danfse", content=b"x" * 33, headers=headers).status_code == 413
    pdf = sessao.post("/api/rtc/danfse", content=b"<NFSe/>", headers=headers)
    assert pdf.status_code == 200
    assert pdf.headers["cache-control"] == "no-store"
    assert pdf.headers["content-disposition"] == 'attachment; filename="danfse.pdf"'
    assert pdf.content == b"%PDF-1.4 teste"
