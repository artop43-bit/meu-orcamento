"""Adaptador HTTP para os motores da Receita executados na rede interna."""

import json
import unicodedata
import uuid
from collections.abc import Iterator, Mapping
from datetime import date
from decimal import Decimal
from functools import lru_cache
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from app.core.config import get_settings
from app.core.errors import AppError
from app.schemas.rtc import Regular, Simples

Motor = Literal["regular", "simples", "danfse"]
Catalogo = Literal["ncm", "nbs", "cst", "classificacao", "atividade", "uf", "municipio"]
MAX_XML = 5 * 1024 * 1024
MAX_RESPOSTA = 8 * 1024 * 1024
DADOS = "/api/calculadora/dados-abertos"
CALCULO = "/api/calculadora/observabilidade"
ATIVIDADES = "/api/calculadora/simples-nacional/atividades"
CALCULADOS = {"CALCULADO", "CALCULO_SIMULADO"}


class SemRedirecionamento(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def consulta_motor(
    motor: Motor,
    caminho: str,
    corpo: bytes | None = None,
    tipo: str = "application/json",
) -> tuple[bytes, Mapping[str, str]]:
    base = getattr(get_settings(), f"rtc_{motor}_url")
    if not base:
        raise AppError(503, "rtc_indisponivel", "Esta ferramenta fiscal está indisponível.")
    requisicao = Request(
        base.rstrip("/") + caminho,
        data=corpo,
        headers={"Content-Type": tipo} if corpo is not None else {},
    )
    try:
        with build_opener(ProxyHandler({}), SemRedirecionamento()).open(
            requisicao, timeout=15
        ) as resposta:
            dados = resposta.read(MAX_RESPOSTA + 1)
            if len(dados) > MAX_RESPOSTA:
                raise AppError(502, "rtc_resposta_invalida", "A resposta fiscal excedeu o limite.")
            return dados, resposta.headers
    except HTTPError as erro:
        with erro:
            if erro.code in {400, 404, 422}:
                if motor == "danfse":
                    raise AppError(
                        422, "rtc_xml_invalido", "O arquivo não é um XML de NFS-e aceito."
                    ) from erro
                dado = ler_json(erro.read(32_768), fallback={})
                if not isinstance(dado, dict):
                    dado = {}
                mensagens = erros_item(dado.get("errors") or dado.get("erros") or [])
                detalhe = dado.get("detail")
                mensagem = " ".join(mensagens[:3]) or (
                    detalhe
                    if isinstance(detalhe, str) and detalhe
                    else "Confira os dados e a vigência informada."
                )
                raise AppError(422, "rtc_dados_invalidos", mensagem[:800]) from erro
            raise AppError(
                503, "rtc_indisponivel", "Não foi possível consultar o motor fiscal."
            ) from erro
    except (URLError, OSError) as erro:
        raise AppError(
            503, "rtc_indisponivel", "Não foi possível consultar o motor fiscal."
        ) from erro


def ler_json(dados: bytes, *, fallback: dict | None = None) -> Any:
    try:
        return json.loads(dados, parse_float=Decimal)
    except (ValueError, UnicodeError) as erro:
        if fallback is not None:
            return fallback
        raise AppError(
            502, "rtc_resposta_invalida", "O motor fiscal retornou dados inválidos."
        ) from erro


def erros_item(erros: list[dict]) -> list[str]:
    return [
        f"{e.get('code', '')} {e.get('detail') or e.get('title') or ''}".strip()
        for e in erros
        if isinstance(e, dict) and (e.get("detail") or e.get("title"))
    ]


def compactar(dados: dict) -> dict:
    return {chave: valor for chave, valor in dados.items() if valor is not None}


def decimal_texto(valor: Any) -> str:
    return format(valor, "f") if isinstance(valor, Decimal) else str(valor)


def base_item(item, numero: int) -> dict:
    return compactar(
        {
            "numero": numero,
            "cClassTrib": item.classificacao,
            "ncm": item.ncm,
            "nbs": item.nbs,
            "baseCalculo": item.base,
        }
    )


def montar_regular(simulacao: Regular, identificador: str) -> tuple[str, dict]:
    itens = []
    for numero, item in enumerate(simulacao.itens, 1):
        entrada = base_item(item, numero)
        entrada.update(
            compactar({"cst": item.cst, "quantidade": item.quantidade, "unidade": item.unidade})
        )
        aliquotas = compactar(
            {"cbs": item.cbs, "ibsEstadual": item.ibs_uf, "ibsMunicipal": item.ibs_municipio}
        )
        if item.seletivo:
            imposto = item.seletivo
            entrada["impostoSeletivo"] = compactar(
                {
                    "cst": imposto.cst,
                    "cClassTrib": imposto.classificacao,
                    "baseCalculo": imposto.base,
                    "quantidade": item.quantidade,
                    "unidade": item.unidade,
                    "impostoInformado": imposto.imposto_informado,
                }
            )
            aliquotas_is = compactar(
                {"adValorem": imposto.aliquota_percentual, "adRem": imposto.aliquota_especifica}
            )
            if aliquotas_is:
                aliquotas["impostoSeletivo"] = aliquotas_is
        if aliquotas:
            entrada["aliquotasNominais"] = aliquotas
        itens.append(entrada)
    return f"{CALCULO}/regime-geral", {
        "id": identificador,
        "versao": "1.0.0",
        "dhFatoGerador": f"{simulacao.data}T12:00:00-03:00",
        "uf": simulacao.uf,
        "municipio": simulacao.municipio,
        "tpDoc": int(simulacao.documento),
        "itens": itens,
    }


def montar_simples(simulacao: Simples, identificador: str) -> tuple[str, dict]:
    caminho = f"{CALCULO}/simples-nacional"
    entrada = {
        "id": identificador,
        "versao": "2.0.0",
        "data": simulacao.data.isoformat(),
        "tpDoc": simulacao.documento,
    }
    if simulacao.documento != "91":
        entrada["CRT"] = simulacao.crt
        entrada["itens"] = [
            base_item(item, numero)
            | compactar(
                {
                    "cAtivSN": item.atividade,
                    "valorImpostoSeletivo": item.valor_is or Decimal(0),
                    "pCBSSN": item.cbs,
                    "pIBSSN": item.ibs,
                }
            )
            for numero, item in enumerate(simulacao.itens, 1)
        ]
        return caminho, entrada

    item = simulacao.itens[0]
    aliquotas = compactar({"fatorR": simulacao.fator_r})
    if simulacao.anexo is not None:
        par = compactar({"pCBSSN": item.cbs, "pIBSSN": item.ibs})
        sem_iss = compactar(
            {
                "pCBSSN": simulacao.cbs_sem_redistribuicao,
                "pIBSSN": simulacao.ibs_sem_redistribuicao,
            }
        )
        if sem_iss:
            par["semRedistribuicaoISS"] = sem_iss
        aliquotas[f"anexo{simulacao.anexo}"] = par
    entrada.update(
        {
            "versao": "3.0.0",
            "opSimpNac": "3",
            "regApIBSCBSSN": "1",
            "regApTribSN": "1",
            "itens": [
                base_item(item, 1)
                | compactar(
                    {
                        "cAtivSN": item.atividade,
                        "tribISSQN": simulacao.tributacao_iss,
                        "tpRetISSQN": simulacao.retencao_iss,
                        "tpBM": simulacao.beneficio_iss,
                    }
                )
            ],
        }
    )
    if aliquotas:
        entrada["aliquotasEfetivas"] = aliquotas
    return f"{caminho}/nao-assistido", entrada


def _textos(valor: Any) -> Iterator[str]:
    if isinstance(valor, str) and valor.strip():
        yield valor
    elif isinstance(valor, dict):
        for item in valor.values():
            yield from _textos(item)
    elif isinstance(valor, list):
        for item in valor:
            yield from _textos(item)


def _tributo(grupo: dict, valor: str, nominal: str, base: Any = None) -> dict | None:
    if grupo.get(valor) is None:
        return None
    return compactar(
        {
            "valor": decimal_texto(grupo[valor]),
            "base": decimal_texto(base) if base is not None else None,
            "aliquota": decimal_texto(grupo[nominal]) if grupo.get(nominal) is not None else None,
            "aliquota_efetiva": (
                decimal_texto(reducao)
                if (reducao := (grupo.get("gRed") or {}).get("pAliqEfet")) is not None
                else None
            ),
        }
    )


def _tributos_regular(grupo: dict, *, total: bool = False) -> dict:
    ibscbs = grupo.get("IBSCBSTot" if total else "IBSCBS") or {}
    calculo = ibscbs if total else (ibscbs.get("gIBSCBS") or {})
    base = calculo.get("vBCIBSCBS" if total else "vBC")
    ibs = (calculo.get("gIBS") or {}) if total else calculo
    seletivo = grupo.get("ISTot" if total else "IS") or {}
    return compactar(
        {
            "cbs": _tributo(calculo.get("gCBS") or {}, "vCBS", "pCBS", base),
            "ibs": _tributo(ibs, "vIBS", "pIBS", base),
            "ibs_uf": _tributo(ibs.get("gIBSUF") or {}, "vIBSUF", "pIBSUF", base),
            "ibs_municipio": _tributo(ibs.get("gIBSMun") or {}, "vIBSMun", "pIBSMun", base),
            "is": _tributo(seletivo, "vIS", "pIS", seletivo.get("vBCIS")),
        }
    )


def _tributos_simples(grupo: dict, *, total: bool = False) -> dict:
    base = grupo.get("vBC")
    suf = "tot" if total else ""
    seletivo = grupo if total else (grupo.get("IS") or {})
    return compactar(
        {
            "cbs": _tributo(grupo, f"vCBSSN{suf}", "pCBSSN", base),
            "ibs": _tributo(grupo, f"vIBSSN{suf}", "pIBSSN", base),
            "is": _tributo(seletivo, "totalIs" if total else "valor", "pIS"),
        }
    )


def resultado_simulacao(
    simulacao: Regular | Simples, dado: dict, headers: Mapping[str, str]
) -> dict:
    normalizar = _tributos_regular if isinstance(simulacao, Regular) else _tributos_simples
    itens = []
    for item in dado["objetos"]:
        tributos = item.get("tribCalc") or {}
        memorias = [tributos.get("memoriaCalculo")]
        for chave in ("IBSCBS", "IS"):
            memorias.append((tributos.get(chave) or {}).get("memoriaCalculo"))
        motivo = item.get("motivoEstado") or {}
        itens.append(
            {
                "numero": item["nObj"],
                "estado": item["estadoItem"],
                "tributos": normalizar(tributos),
                "memoria": list(dict.fromkeys(_textos(memorias))),
                "erros": erros_item(item.get("erros") or []),
                "motivo": next(_textos(motivo), None),
            }
        )
    totais = dado.get("total") or {}
    incompleto = (
        len(itens) != len(simulacao.itens)
        or {i["numero"] for i in itens} != set(range(1, len(simulacao.itens) + 1))
        or any(i["estado"] not in CALCULADOS for i in itens)
    )
    aliquotas_simples = isinstance(simulacao, Simples) and any(
        i.cbs is not None or i.ibs is not None for i in simulacao.itens
    )
    return {
        "itens": itens,
        "parcial": incompleto,
        "simulado": aliquotas_simples
        or bool(headers.get("x-warning-dados-simulados"))
        or any(i["estado"] == "CALCULO_SIMULADO" for i in itens),
        "totais": normalizar(totais.get("tribCalc", totais), total=True),
        "versao_motor": headers.get("X-CALC-APP-VERSION"),
        "versao_base": headers.get("X-CALC-DB-VERSION"),
    }


def simular(simulacao: Regular | Simples) -> dict:
    identificador = uuid.uuid4().hex
    caminho, entrada = (
        montar_regular(simulacao, identificador)
        if isinstance(simulacao, Regular)
        else montar_simples(simulacao, identificador)
    )
    corpo = json.dumps(entrada, default=decimal_texto, allow_nan=False).encode()
    resposta, headers = consulta_motor(simulacao.regime, caminho, corpo)
    dado = ler_json(resposta)
    if not isinstance(dado, dict) or not isinstance(dado.get("objetos"), list):
        raise AppError(502, "rtc_resposta_invalida", "O motor fiscal retornou dados inválidos.")
    return resultado_simulacao(simulacao, dado, headers)


@lru_cache(maxsize=12)
def _dados_publicos(motor: Motor, caminho: str) -> tuple[Any, Mapping[str, str]]:
    corpo, headers = consulta_motor(motor, caminho)
    return ler_json(corpo), headers


def _busca(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", texto.casefold()) if not unicodedata.combining(c)
    )


def referencias(
    tipo: Catalogo, data: date, q: str, uf: str | None, anexo: str | None, doc: str | None
) -> dict:
    motor: Motor = "simples" if tipo == "atividade" else "regular"
    caminho = {
        "ncm": f"{DADOS}/ncm/vigentes",
        "nbs": f"{DADOS}/nbs/lista",
        "cst": f"{DADOS}/situacoes-tributarias/cbs-ibs",
        "classificacao": f"{DADOS}/situacoes-tributarias/cbs-ibs",
        "atividade": ATIVIDADES,
        "uf": f"{DADOS}/ufs",
        "municipio": f"{DADOS}/ufs/municipios",
    }[tipo]
    params = {} if tipo in {"uf", "municipio"} else {"data": data.isoformat()}
    if tipo == "atividade":
        params.update(compactar({"tpDoc": doc, "anexos": anexo}))
    if tipo == "municipio":
        if not uf:
            raise AppError(422, "rtc_uf_obrigatoria", "Escolha a UF para consultar os municípios.")
        params["siglaUf"] = uf
    registros, headers = _dados_publicos(
        motor, f"{caminho}?{urlencode(params)}" if params else caminho
    )
    if tipo == "classificacao":
        registros = [
            c | {"cst": s["codigo"]}
            for s in registros
            for c in s.get("classificacoesTributarias", [])
        ]
    achados = []
    for registro in registros:
        if (
            tipo == "atividade"
            and anexo
            and anexo not in {registro.get("anexoSemFatorR"), registro.get("anexoComFatorR")}
        ):
            continue
        codigo = str(registro.get("sigla") or registro.get("codigo") or registro.get("ncm") or "")
        descricao = registro.get("descricao") or registro.get("nome") or ""
        if not codigo or not all(
            palavra in _busca(f"{codigo} {descricao}") for palavra in _busca(q).split()
        ):
            continue
        achados.append(
            compactar(
                {
                    "codigo": codigo,
                    "descricao": descricao,
                    "cst": registro.get("cst"),
                    "anexo": registro.get("rotuloAnexo"),
                    "anexo_sem_fator_r": registro.get("anexoSemFatorR"),
                    "anexo_com_fator_r": registro.get("anexoComFatorR"),
                    "disponivel": (
                        False
                        if registro.get("admissivelNoDocumento") is False
                        else registro.get("disponivel")
                    ),
                }
            )
        )
    limite = len(achados) if tipo in {"uf", "municipio"} else 50
    versao = headers.get("X-CALC-DB-VERSION")
    if not versao and tipo not in {"uf", "municipio"}:
        dados, _ = _dados_publicos("regular", f"{DADOS}/versao")
        versao = dados.get("versaoDb")
    return {"data": data, "versao_base": versao, "itens": achados[:limite], "total": len(achados)}


def fundamentos(tipo: Literal["cst", "classificacao"], codigo: str, data: date) -> list[dict]:
    registros, _ = _dados_publicos(
        "regular", f"{DADOS}/fundamentacoes-legais?data={data.isoformat()}"
    )
    chave = "codigoSituacaoTributaria" if tipo == "cst" else "codigoClassificacaoTributaria"
    textos = [
        {
            "referencia": r.get("textoCurto") or "",
            "texto": " ".join(
                (r.get("texto") or "", (r.get("referenciaNormativa") or "").replace("\\n", " "))
            ).strip(),
        }
        for r in registros
        if r.get(chave) == codigo and r.get("conjuntoTributo", "CBS e IBS") == "CBS e IBS"
    ]
    # A mesma base normativa pode estar vinculada a vários itens do mesmo CST.
    return list({(r["referencia"], r["texto"]): r for r in textos}.values())


def gerar_danfse(xml: bytes) -> bytes:
    pdf, _ = consulta_motor("danfse", "/api/danfse", xml, "application/xml")
    if not pdf.startswith(b"%PDF-"):
        raise AppError(502, "rtc_resposta_invalida", "O gerador não retornou um PDF válido.")
    return pdf
