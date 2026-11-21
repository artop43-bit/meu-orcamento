import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";

import { errorMessage } from "../../api/client";
import { rtcApi, type Anexo, type Catalogo, type Documento, type Referencia } from "../../api/rtc";
import { Alert, Button } from "../ui";

export const ANEXOS: Anexo[] = ["I", "II", "III", "IV", "V"];
export const CATALOGOS = {
  ncm: "Mercadorias (NCM)",
  nbs: "Serviços (NBS)",
  cst: "Situação tributária (CST)",
  classificacao: "Classificação tributária (cClassTrib)",
  atividade: "Atividades do Simples Nacional",
} satisfies Partial<Record<Catalogo, string>>;
export type CatalogoFiscal = keyof typeof CATALOGOS;

function Fundamentos({ tipo, codigo, data }: { tipo: "cst" | "classificacao"; codigo: string; data: string }) {
  const query = useQuery({
    queryKey: ["rtc", "fundamentos", tipo, codigo, data],
    queryFn: () => rtcApi.fundamentos(tipo, codigo, data),
    retry: false,
  });
  if (query.isPending) return <p role="status">Consultando fundamentação…</p>;
  if (query.isError) return <Alert tone="error">{errorMessage(query.error)}</Alert>;
  if (query.data.length === 0) return <p className="muted small">A base não traz fundamentação para este código na data escolhida.</p>;
  return (
    <div className="stack stack--tight">
      {query.data.map((item, index) => (
        <div key={index}>
          {item.referencia && <strong>{item.referencia}</strong>}
          {item.texto && <p>{item.texto}</p>}
        </div>
      ))}
    </div>
  );
}

export function Referencias({ tipo, data, documento, selecionar }: {
  tipo: CatalogoFiscal;
  data: string;
  documento?: Documento;
  selecionar?: (referencia: Referencia) => void;
}) {
  const [termo, setTermo] = useState("");
  const [anexo, setAnexo] = useState("");
  const [busca, setBusca] = useState({ texto: "", anexo: "" });
  const [escolhido, setEscolhido] = useState<string | null>(null);
  const query = useQuery({
    queryKey: ["rtc", "referencias", tipo, data, documento, busca],
    queryFn: () => rtcApi.referencias(tipo, {
      data, q: busca.texto, ...(busca.anexo ? { anexo: busca.anexo } : {}),
      ...(documento ? { documento } : {}),
    }),
    enabled: Boolean(data),
    staleTime: 5 * 60_000,
    retry: false,
  });

  function buscar(event: FormEvent) {
    event.preventDefault();
    setBusca({ texto: termo.trim(), anexo });
    setEscolhido(null);
    if (query.isError && busca.texto === termo.trim() && busca.anexo === anexo) void query.refetch();
  }

  return (
    <div className="stack">
      <form className="inline-form stack stack--tight" onSubmit={buscar}>
        <label className="field">
          <span className="field-label">Buscar por código ou descrição</span>
          <input type="search" maxLength={100} value={termo} onChange={(e) => setTermo(e.target.value)} />
        </label>
        {tipo === "atividade" && (
          <label className="field">
            <span className="field-label">Anexo</span>
            <select value={anexo} onChange={(e) => setAnexo(e.target.value)}>
              <option value="">Todos</option>
              {ANEXOS.map((valor) => <option key={valor}>{valor}</option>)}
            </select>
          </label>
        )}
        <div className="form-actions"><Button type="submit" variant="secondary" disabled={!data} loading={query.isFetching}>Buscar</Button></div>
      </form>
      {!data && <p className="muted">Informe a data para consultar os códigos vigentes.</p>}
      {query.isFetching && <p role="status" className="muted">Consultando a base fiscal…</p>}
      {query.isError && <Alert tone="error">{errorMessage(query.error)}</Alert>}
      {query.data && (
        <>
          <p className="muted small">
            {query.data.total === 0 ? "Nenhum resultado para esta busca." : <>
              Vigentes em {new Date(`${data}T12:00:00`).toLocaleDateString("pt-BR")}.
              {query.data.total > query.data.itens.length && ` Mostrando ${query.data.itens.length} de ${query.data.total}. Refine a busca.`}
            </>}
            {query.data.versao_base && ` Base fiscal ${query.data.versao_base}.`}
          </p>
          {query.data.itens.length > 0 && <ul className="items">
            {query.data.itens.map((item) => (
              <li className="item item--stack" key={`${item.cst ?? ""}-${item.codigo}`}>
                <div>
                  <strong>{item.codigo}</strong> · {item.descricao}
                  {item.anexo && <p className="muted small">Anexo {item.anexo}</p>}
                  {selecionar && item.disponivel === false && <p className="muted small">Indisponível para este documento.</p>}
                </div>
                <div className="form-actions">
                  {(tipo === "cst" || tipo === "classificacao") && (
                    <Button type="button" variant="secondary" aria-expanded={escolhido === item.codigo} onClick={() => setEscolhido(escolhido === item.codigo ? null : item.codigo)}>
                      Fundamentação de {item.codigo}
                    </Button>
                  )}
                  {selecionar && item.disponivel !== false && (
                    <Button type="button" onClick={() => selecionar(item)}>Usar {item.codigo}</Button>
                  )}
                </div>
                {(tipo === "cst" || tipo === "classificacao") && escolhido === item.codigo && (
                  <Fundamentos tipo={tipo} codigo={item.codigo} data={data} />
                )}
              </li>
            ))}
          </ul>}
        </>
      )}
    </div>
  );
}
