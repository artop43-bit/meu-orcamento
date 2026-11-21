"""Confere os contratos do Meu Orçamento com os três motores oficiais."""

import os
import sys
import time
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.core.errors import AppError
from app.schemas.rtc import Regular, Simples
from app.services import rtc

DATA_2026 = date(2026, 11, 20)
DATA_2027 = date(2027, 3, 15)


def aguardar(motor, rota):
    limite = time.monotonic() + 360
    while True:
        try:
            rtc.consulta_motor(motor, rota)
            return
        except AppError:
            if time.monotonic() >= limite:
                raise
            time.sleep(3)


def regular():
    aguardar("regular", f"{rtc.DADOS}/versao")
    nominal = {"cbs": "8.8", "ibs_uf": "0.05", "ibs_municipio": "0.05"}
    entrada = Regular(
        regime="regular",
        data=DATA_2027,
        documento="55",
        municipio=4314902,
        uf="RS",
        itens=[
            {
                "ncm": "22030000",
                "cst": "000",
                "classificacao": "000001",
                "quantidade": "12",
                "unidade": "LT",
                **nominal,
                "seletivo": {
                    "cst": "000",
                    "classificacao": "000001",
                    "base": "150.00",
                    "imposto_informado": "15.00",
                    "aliquota_percentual": "10",
                },
            },
            {
                "ncm": "02013000",
                "cst": "200",
                "classificacao": "200035",
                "base": "80.00",
                **nominal,
            },
        ],
    )
    resultado = rtc.simular(entrada)
    assert resultado["parcial"] and resultado["simulado"], resultado
    assert resultado["itens"][0]["memoria"], resultado
    assert Decimal(resultado["totais"]["is"]["valor"]) == Decimal("15.00"), resultado
    assert Decimal(resultado["totais"]["cbs"]["valor"]) == Decimal("14.52"), resultado
    assert resultado["itens"][1]["estado"] == "INCONSISTENCIA_ENTRADA", resultado
    for tipo, termo in [("ncm", "09012100"), ("nbs", "construcao"), ("classificacao", "000001")]:
        tabela = rtc.referencias(tipo, DATA_2026, termo, None, None, None)
        assert tabela["itens"] and tabela["versao_base"], tipo
    cidades = rtc.referencias("municipio", DATA_2026, "", "SP", None, None)
    assert len(cidades["itens"]) > 600
    assert rtc.fundamentos("classificacao", "000001", DATA_2026)
    print("Regime Regular, tabelas e fundamentação: OK")


def simples():
    aguardar("simples", f"{rtc.ATIVIDADES}?data={DATA_2027}")
    atividades = rtc.referencias("atividade", DATA_2027, "07", None, "III", "91")
    assert atividades["itens"][0]["disponivel"], atividades
    nfe = Simples(
        regime="simples",
        data=DATA_2027,
        documento="55",
        itens=[
            {
                "atividade": "01",
                "classificacao": "000001",
                "base": "950.00",
                "valor_is": "50.00",
                "ibs": "1.25",
                "cbs": "2.75",
            }
        ],
    )
    nfse = Simples(
        regime="simples",
        data=DATA_2027,
        documento="91",
        anexo="III",
        itens=[
            {
                "atividade": "07",
                "classificacao": "000001",
                "base": "10000.00",
                "ibs": "0.0257",
                "cbs": "2.2154",
            }
        ],
    )
    for entrada, ibs, cbs in [(nfe, "11.88", "26.12"), (nfse, "3.00", "222.00")]:
        resultado = rtc.simular(entrada)
        assert not resultado["parcial"] and resultado["simulado"], resultado
        assert resultado["versao_base"], resultado
        assert resultado["totais"]["ibs"]["valor"] == ibs, resultado
        assert resultado["totais"]["cbs"]["valor"] == cbs, resultado
        if entrada.documento == "55":
            assert resultado["itens"][0]["tributos"]["is"]["valor"] == "50.00", resultado
    print("Simples Nacional, NF-e, NFS-e e atividades: OK")


def danfse():
    aguardar("danfse", "/health/ready")
    xml = Path(os.environ.get("RTC_SMOKE_XML", "/rtc/nfse-teste.xml")).read_bytes()
    pdf = rtc.gerar_danfse(xml)
    assert pdf.endswith(b"%%EOF\n"), len(pdf)
    print("DANFSe a partir de XML fictício: OK")


funcoes = {"regular": regular, "simples": simples, "danfse": danfse}
for motor in sys.argv[1:] or funcoes:
    funcoes[motor]()
