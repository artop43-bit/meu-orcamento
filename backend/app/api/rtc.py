from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from starlette.concurrency import run_in_threadpool

from app.api.deps import CurrentUser, require_solution
from app.core.errors import AppError
from app.core.rate_limit import rate_limit
from app.schemas.rtc import Anexo, Documento, SimulacaoRtc, Uf
from app.services import rtc

router = APIRouter(
    prefix="/rtc",
    tags=["reforma tributária"],
    dependencies=[Depends(require_solution("meu-orcamento"))],
)


@router.post("/simular", dependencies=[Depends(rate_limit("rtc_simular", 30, 60))])
def simular(body: SimulacaoRtc, _: CurrentUser) -> dict:
    return rtc.simular(body)


@router.get("/referencias/{tipo}", dependencies=[Depends(rate_limit("rtc_referencia", 120, 60))])
def referencias(
    tipo: rtc.Catalogo,
    data: date,
    _: CurrentUser,
    q: Annotated[str, Query(max_length=100)] = "",
    uf: Uf | None = None,
    anexo: Anexo | None = None,
    documento: Documento | None = None,
) -> dict:
    return rtc.referencias(tipo, data, q, uf, anexo, documento)


@router.get("/fundamentos", dependencies=[Depends(rate_limit("rtc_fundamentos", 60, 60))])
def fundamentos(
    tipo: Literal["cst", "classificacao"],
    codigo: Annotated[str, Query(pattern=r"^(\d{3}|\d{6})$")],
    data: date,
    _: CurrentUser,
) -> list[dict]:
    return rtc.fundamentos(tipo, codigo, data)


@router.post("/danfse", dependencies=[Depends(rate_limit("rtc_danfse", 12, 60))])
async def danfse(request: Request, _: CurrentUser) -> Response:
    if request.headers.get("content-type", "").split(";", 1)[0] not in {
        "text/xml",
        "application/xml",
    }:
        raise AppError(415, "rtc_tipo_invalido", "Selecione um arquivo XML de NFS-e.")
    dados = bytearray()
    async for parte in request.stream():
        if len(dados) + len(parte) > rtc.MAX_XML:
            raise AppError(413, "rtc_xml_grande", "O XML pode ter até 5 MB.")
        dados.extend(parte)
    if not dados.strip():
        raise AppError(422, "rtc_xml_vazio", "Selecione um arquivo XML com o conteúdo da NFS-e.")
    pdf = await run_in_threadpool(rtc.gerar_danfse, bytes(dados))
    return Response(
        pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="danfse.pdf"',
            "Cache-Control": "no-store",
        },
    )
