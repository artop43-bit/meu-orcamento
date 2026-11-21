"""Entradas da ferramenta RTC. A Receita valida o enquadramento de cada item."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Valor = Annotated[Decimal, Field(ge=0, max_digits=15, decimal_places=2)]
Quantidade = Annotated[Decimal, Field(gt=0, max_digits=15, decimal_places=4)]
Aliquota = Annotated[Decimal, Field(ge=0, lt=1000, decimal_places=34, allow_inf_nan=False)]
CodigoCst = Annotated[str, StringConstraints(pattern=r"^\d{3}$")]
CodigoClassificacao = Annotated[str, StringConstraints(pattern=r"^\d{6}$")]
Uf = Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")]
Documento = Literal["55", "65", "91"]
Anexo = Literal["I", "II", "III", "IV", "V"]


class EntradaRtc(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ImpostoSeletivo(EntradaRtc):
    cst: CodigoCst
    classificacao: CodigoClassificacao
    base: Valor
    aliquota_percentual: Aliquota | None = None
    aliquota_especifica: Aliquota | None = None
    imposto_informado: Valor | None = None


class ItemRtc(EntradaRtc):
    classificacao: CodigoClassificacao
    ncm: Annotated[str, StringConstraints(pattern=r"^\d{8}$")] | None = None
    nbs: Annotated[str, StringConstraints(pattern=r"^\d{9}$")] | None = None
    base: Valor

    @model_validator(mode="after")
    def um_codigo_de_nomenclatura(self):
        if self.ncm and self.nbs:
            raise ValueError("Preencha NCM para mercadoria ou NBS para serviço.")
        return self


class ItemRegular(ItemRtc):
    base: Valor | None = None
    cst: CodigoCst
    quantidade: Quantidade | None = None
    unidade: Annotated[str, StringConstraints(max_length=12)] | None = None
    cbs: Aliquota | None = None
    ibs_uf: Aliquota | None = None
    ibs_municipio: Aliquota | None = None
    seletivo: ImpostoSeletivo | None = None

    @model_validator(mode="after")
    def base_para_ibs_cbs(self):
        if self.base is None and self.seletivo is None:
            raise ValueError("Preencha a base de cálculo de IBS e CBS.")
        return self


class ItemSimples(ItemRtc):
    atividade: Annotated[str, StringConstraints(pattern=r"^\d{2}$")]
    valor_is: Valor | None = None
    cbs: Aliquota | None = None
    ibs: Aliquota | None = None


class Regular(EntradaRtc):
    regime: Literal["regular"]
    data: date
    documento: Documento
    uf: Uf
    municipio: Annotated[int, Field(ge=1000000, le=9999999)]
    itens: Annotated[list[ItemRegular], Field(min_length=1, max_length=25)]


class Simples(EntradaRtc):
    regime: Literal["simples"]
    data: date
    documento: Documento
    crt: Literal["1", "2"] = "1"
    itens: Annotated[list[ItemSimples], Field(min_length=1, max_length=25)]
    anexo: Anexo | None = None
    fator_r: bool | None = None
    tributacao_iss: Literal["1", "2", "3", "4"] = "1"
    retencao_iss: Literal["1", "2", "3"] = "1"
    beneficio_iss: Literal["1", "2"] | None = None
    cbs_sem_redistribuicao: Aliquota | None = None
    ibs_sem_redistribuicao: Aliquota | None = None

    @model_validator(mode="after")
    def campos_de_servico(self):
        if self.documento == "91" and len(self.itens) != 1:
            raise ValueError("A NFS-e aceita um item por operação.")
        return self


SimulacaoRtc = Annotated[Regular | Simples, Field(discriminator="regime")]
