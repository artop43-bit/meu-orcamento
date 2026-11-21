import { api, ApiError } from "./client";

export type Documento = "55" | "65" | "91";
export type Anexo = "I" | "II" | "III" | "IV" | "V";
export type Catalogo = "ncm" | "nbs" | "cst" | "classificacao" | "atividade" | "uf" | "municipio";

export type Referencia = {
  codigo: string;
  descricao: string;
  cst?: string;
  anexo?: string;
  anexo_sem_fator_r?: Anexo;
  anexo_com_fator_r?: Anexo;
  disponivel?: boolean;
};

export type Referencias = { data: string; versao_base?: string; itens: Referencia[]; total: number };
export type Fundamento = { referencia: string; texto: string };
export type Tributo = { valor: string; base?: string; aliquota?: string; aliquota_efetiva?: string };
export type Tributos = Partial<Record<"cbs" | "ibs" | "ibs_uf" | "ibs_municipio" | "is", Tributo>>;
export type Simulacao = {
  simulado: boolean;
  parcial: boolean;
  totais: Tributos;
  versao_base?: string;
  versao_motor?: string;
  itens: {
    numero: number;
    estado: string;
    tributos: Tributos;
    memoria: string[];
    erros: string[];
    motivo?: string;
  }[];
};

export const rtcApi = {
  simular: (body: unknown) => api.post<Simulacao>("/rtc/simular", body),
  referencias: (tipo: Catalogo, params: Record<string, string>) =>
    api.get<Referencias>(`/rtc/referencias/${tipo}?${new URLSearchParams(params)}`),
  fundamentos: (tipo: "cst" | "classificacao", codigo: string, data: string) =>
    api.get<Fundamento[]>(`/rtc/fundamentos?${new URLSearchParams({ tipo, codigo, data })}`),
};

export const MAX_XML_BYTES = 5 * 1024 * 1024;

export async function gerarDanfse(xml: File) {
  const response = await fetch("/api/rtc/danfse", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/xml", "X-Requested-With": "fetch" },
    body: xml,
  }).catch(() => {
    throw new Error("Não foi possível enviar o XML. Confira a conexão e tente novamente.");
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new ApiError(response.status, data?.error ?? "error", data?.message ?? "Não foi possível gerar o PDF.");
  }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = "danfse.pdf";
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
