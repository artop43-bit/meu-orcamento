import { useRef, useState, type FormEvent, type ReactNode } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Plus, Search, Trash2 } from "lucide-react";

import { errorMessage } from "../../api/client";
import { rtcApi, type Anexo, type Documento, type Referencia, type Simulacao, type Tributos } from "../../api/rtc";
import { money, parseMoney, todayISO } from "../../lib/format";
import { Alert, Button, Sheet } from "../ui";
import { ANEXOS, CATALOGOS, Referencias, type CatalogoFiscal } from "./Referencias";

const DOCUMENTOS: Record<Documento, string> = {
  "55": "NF-e · nota de mercadorias", "65": "NFC-e · nota ao consumidor", "91": "NFS-e · nota de serviços",
};
const TRIBUTOS: Record<keyof Tributos, string> = {
  cbs: "CBS", ibs: "IBS", ibs_uf: "IBS estadual", ibs_municipio: "IBS municipal", is: "Imposto Seletivo",
};

type Item = ReturnType<typeof novoItem>;
type Lookup = { tipo: CatalogoFiscal; item: number };

function novoItem(id: number) {
  return {
    id, tipo: "" as "" | "ncm" | "nbs", codigo: "", cst: "", classificacao: "", atividade: "",
    base: "", cbs: "", ibs: "", ibs_uf: "", ibs_municipio: "", quantidade: "", unidade: "", valor_is: "",
    incluir_is: false, is_cst: "", is_classificacao: "", is_base: "", is_percentual: "", is_especifica: "", is_informado: "",
  };
}

function moeda(valor: string) {
  if (!valor.trim()) return undefined;
  const normalizado = parseMoney(valor);
  if (normalizado === null) throw new Error("Confira os campos de valor em reais.");
  return normalizado;
}

function decimal(valor: string) {
  const normalizado = valor.trim().replace(",", ".");
  if (!normalizado) return undefined;
  if (!/^\d+(?:\.\d+)?$/.test(normalizado)) throw new Error("Informe alíquotas e quantidades com números válidos.");
  return normalizado;
}

function Campo({ rotulo, children }: { rotulo: string; children: ReactNode }) {
  return <label className="field"><span className="field-label">{rotulo}</span>{children}</label>;
}

function Valor({ rotulo, valor, mudar, obrigatorio = false }: {
  rotulo: string; valor: string; mudar: (novo: string) => void; obrigatorio?: boolean;
}) {
  return <Campo rotulo={rotulo}><input inputMode="decimal" value={valor} onChange={(e) => mudar(e.target.value)} required={obrigatorio} maxLength={40} /></Campo>;
}

function Codigo({ rotulo, valor, mudar, digitos, buscar }: {
  rotulo: string; valor: string; mudar: (novo: string) => void; digitos: number; buscar?: () => void;
}) {
  return (
    <div className="stack stack--tight">
      <Campo rotulo={rotulo}>
        <input inputMode="numeric" value={valor} onChange={(e) => mudar(e.target.value.replace(/[^0-9]/g, "").slice(0, digitos))} required pattern={`[0-9]{${digitos}}`} />
      </Campo>
      {buscar && <Button type="button" variant="secondary" onClick={buscar}><Search size={15} aria-hidden /> Consultar {rotulo}</Button>}
    </div>
  );
}

function QuadrosDeTributos({ tributos }: { tributos: Tributos }) {
  const valores = (Object.keys(TRIBUTOS) as (keyof Tributos)[]).filter((chave) => tributos[chave]);
  if (valores.length === 0) return null;
  return (
    <dl className="stats">
      {valores.map((chave) => {
        const tributo = tributos[chave]!;
        return (
          <div className="stat" key={chave}>
            <dt>{TRIBUTOS[chave]}</dt>
            <dd><strong>{money(tributo.valor)}</strong></dd>
            {tributo.base != null && <dd className="muted small">Base {money(tributo.base)}</dd>}
            {tributo.aliquota != null && <dd className="muted small">Alíquota {String(tributo.aliquota).replace(".", ",")}%</dd>}
            {tributo.aliquota_efetiva != null && <dd className="muted small">Efetiva {String(tributo.aliquota_efetiva).replace(".", ",")}%</dd>}
          </div>
        );
      })}
    </dl>
  );
}

function Resultado({ resultado }: { resultado: Simulacao }) {
  const estados: Record<string, string> = {
    CALCULADO: "Calculado", CALCULO_SIMULADO: "Calculado com alíquotas informadas",
    NAO_CALCULADO: "Sem cálculo", INCONSISTENCIA_ENTRADA: "Dados a conferir",
    NAO_IMPLEMENTADO: "Operação sem suporte no motor", FALHA_TECNICA: "Falha no cálculo", SOMENTE_RECEITA: "Somente receita",
  };
  const temTotal = Object.keys(resultado.totais).length > 0;
  return (
    <section className="card stack" aria-label="Resultado da simulação">
      <h3>{resultado.parcial ? "Resultado parcial" : "Resultado da simulação"}</h3>
      {resultado.parcial && <Alert tone="info">Confira os itens abaixo. Os totais consideram apenas os valores calculados pelo motor.</Alert>}
      {resultado.simulado && <p className="muted">Esta estimativa usa alíquotas informadas para o cenário.</p>}
      {temTotal && <QuadrosDeTributos tributos={resultado.totais} />}
      <ul className="items">
        {resultado.itens.map((item) => (
          <li key={item.numero} className="item item--stack">
            <div className="split"><strong>Item {item.numero}</strong><span className="muted">{estados[item.estado] ?? item.estado}</span></div>
            {item.motivo && <p className="muted">{item.motivo}</p>}
            {item.erros.length > 0 && <Alert tone="error"><ul>{item.erros.map((erro, index) => <li key={index}>{erro}</li>)}</ul></Alert>}
            <QuadrosDeTributos tributos={item.tributos} />
            {item.memoria.length > 0 && <details className="details"><summary>Memória de cálculo</summary><ul>{item.memoria.map((texto, i) => <li key={i}>{texto}</li>)}</ul></details>}
          </li>
        ))}
      </ul>
      {(resultado.versao_base || resultado.versao_motor) && <p className="muted small">{resultado.versao_base && `Base fiscal ${resultado.versao_base}. `}{resultado.versao_motor && `Motor ${resultado.versao_motor}.`}</p>}
    </section>
  );
}

export function SimuladorRtc() {
  const [regime, setRegime] = useState<"regular" | "simples">("regular");
  const [data, setData] = useState(todayISO);
  const [documento, setDocumento] = useState<Documento>("55");
  const [uf, setUf] = useState("");
  const [municipio, setMunicipio] = useState("");
  const [crt, setCrt] = useState("1");
  const [anexo, setAnexo] = useState<Anexo | "">("");
  const [fatorR, setFatorR] = useState("");
  const [tributacaoIss, setTributacaoIss] = useState("1");
  const [retencaoIss, setRetencaoIss] = useState("1");
  const [beneficioIss, setBeneficioIss] = useState("");
  const [cbsSemIss, setCbsSemIss] = useState("");
  const [ibsSemIss, setIbsSemIss] = useState("");
  const [itens, setItens] = useState([novoItem(1)]);
  const [lookup, setLookup] = useState<Lookup | null>(null);
  const [erro, setErro] = useState("");
  const sequencia = useRef(1);
  const regular = regime === "regular";
  const nfseSimples = !regular && documento === "91";
  const taxasRegular = Number(data.slice(0, 4)) >= 2027;
  const simulacao = useMutation({ mutationFn: rtcApi.simular });
  const ufs = useQuery({ queryKey: ["rtc", "ufs"], queryFn: () => rtcApi.referencias("uf", { data: "2026-01-01" }), enabled: regular, retry: false, staleTime: 3600_000 });
  const municipios = useQuery({ queryKey: ["rtc", "municipios", uf], queryFn: () => rtcApi.referencias("municipio", { data: "2026-01-01", uf }), enabled: regular && Boolean(uf), retry: false, staleTime: 3600_000 });

  function mudarItem(id: number, parte: Partial<Item>) {
    simulacao.reset();
    setItens((atual) => atual.map((item) => item.id === id ? { ...item, ...parte } : item));
  }

  function usarReferencia(r: Referencia) {
    if (!lookup) return;
    if (lookup.tipo === "ncm" || lookup.tipo === "nbs") mudarItem(lookup.item, { codigo: r.codigo.replace(/\D/g, "") });
    if (lookup.tipo === "cst") mudarItem(lookup.item, { cst: r.codigo, classificacao: "" });
    if (lookup.tipo === "classificacao") mudarItem(lookup.item, { classificacao: r.codigo, ...(r.cst ? { cst: r.cst } : {}) });
    if (lookup.tipo === "atividade") {
      mudarItem(lookup.item, { atividade: r.codigo });
      setAnexo(r.anexo_sem_fator_r && !r.anexo_com_fator_r ? r.anexo_sem_fator_r : "");
    }
    setLookup(null);
  }

  function enviar(event: FormEvent) {
    event.preventDefault();
    if (simulacao.isPending) return;
    setErro("");
    simulacao.reset();
    try {
      const body = {
        regime, data, documento,
        ...(regular ? { uf, municipio: Number(municipio) } : nfseSimples ? {
          anexo: anexo || undefined, fator_r: fatorR ? fatorR === "sim" : undefined,
          tributacao_iss: tributacaoIss, retencao_iss: retencaoIss, beneficio_iss: beneficioIss || undefined,
          cbs_sem_redistribuicao: decimal(cbsSemIss), ibs_sem_redistribuicao: decimal(ibsSemIss),
        } : { crt }),
        itens: itens.map((i) => ({
          classificacao: i.classificacao,
          ...(i.tipo ? { [i.tipo]: i.codigo } : {}), base: moeda(i.base),
          ...(regular ? {
            cst: i.cst, quantidade: decimal(i.quantidade), unidade: i.unidade || undefined,
            ...(taxasRegular ? { cbs: decimal(i.cbs), ibs_uf: decimal(i.ibs_uf), ibs_municipio: decimal(i.ibs_municipio) } : {}),
            ...(i.incluir_is ? { seletivo: {
              cst: i.is_cst, classificacao: i.is_classificacao, base: moeda(i.is_base), imposto_informado: moeda(i.is_informado),
              ...(taxasRegular ? { aliquota_percentual: decimal(i.is_percentual), aliquota_especifica: decimal(i.is_especifica) } : {}),
            } } : {}),
          } : { atividade: i.atividade, cbs: decimal(i.cbs), ibs: decimal(i.ibs), ...(!nfseSimples ? { valor_is: moeda(i.valor_is) } : {}) }),
        })),
      };
      simulacao.mutate(body);
    } catch (e) {
      setErro(errorMessage(e));
    }
  }

  return (
    <div className="stack">
      <form className="stack" onSubmit={enviar} onChange={() => { if (!simulacao.isPending) simulacao.reset(); }}>
        <section className="card stack" aria-label="Operação">
          <h3 className="field-label" style={{ margin: 0 }}>Operação</h3>
          <fieldset className="radios stack" disabled={simulacao.isPending}>
          <div className="grid-2">
            <Campo rotulo="Regime de IBS e CBS">
              <select value={regime} onChange={(e) => {
                const novo = e.target.value as typeof regime;
                setRegime(novo);
                setItens((atual) => (novo === "simples" && documento === "91" ? atual.slice(0, 1) : atual)
                  .map((item) => ({ ...item, cbs: "", ibs: "" })));
              }}><option value="regular">Regime Regular</option><option value="simples">Simples Nacional</option></select>
            </Campo>
            <Campo rotulo="Data da operação"><input type="date" value={data} onChange={(e) => setData(e.target.value)} required /></Campo>
            <Campo rotulo="Documento fiscal">
              <select value={documento} onChange={(e) => {
                const doc = e.target.value as Documento;
                setDocumento(doc);
                if (doc === "91" && !regular) setItens((atual) => atual.slice(0, 1));
              }}>{Object.entries(DOCUMENTOS).map(([doc, nome]) => <option key={doc} value={doc}>{nome}</option>)}</select>
            </Campo>
            {!regular && !nfseSimples && <Campo rotulo="Situação no Simples">
              <select value={crt} onChange={(e) => setCrt(e.target.value)}><option value="1">Simples Nacional</option><option value="2">Excesso de sublimite</option></select>
            </Campo>}
            {regular && <>
              <Campo rotulo="UF da operação">
                <select required value={uf} onChange={(e) => { setUf(e.target.value); setMunicipio(""); }}>
                  <option value="">Selecione a UF</option>{ufs.data?.itens.map((u) => <option key={u.codigo} value={u.codigo}>{u.descricao}</option>)}
                </select>
              </Campo>
              <Campo rotulo="Município da operação">
                <select required value={municipio} disabled={!uf || municipios.isPending} onChange={(e) => setMunicipio(e.target.value)}>
                  <option value="">Selecione o município</option>{municipios.data?.itens.map((m) => <option key={m.codigo} value={m.codigo}>{m.descricao}</option>)}
                </select>
              </Campo>
            </>}
          </div>
          {ufs.isError && regular && <Alert tone="error">{errorMessage(ufs.error)} <Button type="button" variant="secondary" onClick={() => void ufs.refetch()}>Tentar novamente</Button></Alert>}
          {municipios.isError && regular && <Alert tone="error">{errorMessage(municipios.error)} <Button type="button" variant="secondary" onClick={() => void municipios.refetch()}>Tentar novamente</Button></Alert>}
          {nfseSimples && <p className="muted small">Para NFS-e de ME ou EPP com IBS e CBS pelo Simples. Informe uma operação de serviço por vez.</p>}
          {regular && taxasRegular && <Alert tone="info">Para esta data, informe as alíquotas do cenário em cada item.</Alert>}
          </fieldset>
        </section>
        {itens.map((item, index) => {
          const mudar = (parte: Partial<Item>) => mudarItem(item.id, parte);
          const buscar = (tipo: CatalogoFiscal) => () => setLookup({ tipo, item: item.id });
          return (
            <section className="card stack" key={item.id} aria-label={`Item ${index + 1}`}>
              <h3 className="field-label" style={{ margin: 0 }}>Item {index + 1}</h3>
              <fieldset className="radios stack" disabled={simulacao.isPending}>
              <div className="grid-2">
                <Valor rotulo="Base de cálculo (R$)" valor={item.base} mudar={(base) => mudar({ base })} obrigatorio={!regular || !item.incluir_is} />
                <Campo rotulo="Código de mercadoria ou serviço">
                  <select value={item.tipo} onChange={(e) => mudar({ tipo: e.target.value as Item["tipo"], codigo: "" })}>
                    <option value="">Sem código informado</option><option value="ncm">Mercadoria (NCM)</option><option value="nbs">Serviço (NBS)</option>
                  </select>
                </Campo>
                {item.tipo && <Codigo rotulo={item.tipo.toUpperCase()} valor={item.codigo} digitos={item.tipo === "ncm" ? 8 : 9} mudar={(codigo) => mudar({ codigo })} buscar={buscar(item.tipo)} />}
                {regular && <Codigo rotulo="CST" valor={item.cst} digitos={3} mudar={(cst) => mudar({ cst })} buscar={buscar("cst")} />}
                <Codigo rotulo="cClassTrib" valor={item.classificacao} digitos={6} mudar={(classificacao) => mudar({ classificacao })} buscar={buscar("classificacao")} />
                {!regular && <Codigo rotulo="Atividade do Simples" valor={item.atividade} digitos={2} mudar={(atividade) => mudar({ atividade })} buscar={buscar("atividade")} />}
                {(!regular || taxasRegular) && <Valor rotulo={regular ? "Alíquota CBS (%)" : "Alíquota efetiva CBS (%)"} valor={item.cbs} mudar={(cbs) => mudar({ cbs })} />}
                {!regular && <Valor rotulo="Alíquota efetiva IBS (%)" valor={item.ibs} mudar={(ibs) => mudar({ ibs })} />}
                {regular && taxasRegular && <>
                  <Valor rotulo="Alíquota IBS estadual (%)" valor={item.ibs_uf} mudar={(ibs_uf) => mudar({ ibs_uf })} />
                  <Valor rotulo="Alíquota IBS municipal (%)" valor={item.ibs_municipio} mudar={(ibs_municipio) => mudar({ ibs_municipio })} />
                </>}
                {!regular && !nfseSimples && <Valor rotulo="Imposto Seletivo informado (R$)" valor={item.valor_is} mudar={(valor_is) => mudar({ valor_is })} />}
              </div>
              {regular && <details className="details">
                <summary>Quantidade e Imposto Seletivo</summary>
                <div className="stack">
                  <div className="grid-2">
                    <Valor rotulo="Quantidade" valor={item.quantidade} mudar={(quantidade) => mudar({ quantidade })} />
                    <Campo rotulo="Unidade"><input value={item.unidade} maxLength={12} onChange={(e) => mudar({ unidade: e.target.value })} /></Campo>
                  </div>
                  <label className="row"><input type="checkbox" checked={item.incluir_is} onChange={(e) => mudar({ incluir_is: e.target.checked })} /> Incluir Imposto Seletivo</label>
                  {item.incluir_is && <p className="muted small">Deixe a base de IBS e CBS em branco para o motor derivá-la dos valores do Imposto Seletivo.</p>}
                  {item.incluir_is && <div className="grid-2">
                    <Codigo rotulo="CST do Imposto Seletivo" valor={item.is_cst} digitos={3} mudar={(is_cst) => mudar({ is_cst })} />
                    <Codigo rotulo="cClassTrib do Imposto Seletivo" valor={item.is_classificacao} digitos={6} mudar={(is_classificacao) => mudar({ is_classificacao })} />
                    <Valor rotulo="Base do Imposto Seletivo (R$)" valor={item.is_base} mudar={(is_base) => mudar({ is_base })} obrigatorio />
                    <Valor rotulo="Imposto informado (R$)" valor={item.is_informado} mudar={(is_informado) => mudar({ is_informado })} />
                    {taxasRegular && <>
                      <Valor rotulo="Alíquota percentual do IS (%)" valor={item.is_percentual} mudar={(is_percentual) => mudar({ is_percentual })} />
                      <Valor rotulo="Alíquota específica do IS por unidade" valor={item.is_especifica} mudar={(is_especifica) => mudar({ is_especifica })} />
                    </>}
                  </div>}
                </div>
              </details>}
              {nfseSimples && <details className="details" open>
                <summary>Anexo e dados do ISS da NFS-e</summary>
                <div className="grid-2">
                  <Campo rotulo="Anexo das alíquotas informadas"><select value={anexo} onChange={(e) => setAnexo(e.target.value as Anexo | "")}><option value="">Selecione</option>{ANEXOS.map((a) => <option key={a}>{a}</option>)}</select></Campo>
                  <Campo rotulo="Atingiu o Fator R?"><select value={fatorR} onChange={(e) => setFatorR(e.target.value)}><option value="">Não se aplica</option><option value="sim">Sim</option><option value="nao">Não</option></select></Campo>
                  <Campo rotulo="Tributação do ISS"><select value={tributacaoIss} onChange={(e) => setTributacaoIss(e.target.value)}><option value="1">Operação tributável</option><option value="2">Imunidade</option><option value="3">Exportação de serviço</option><option value="4">Não incidência</option></select></Campo>
                  <Campo rotulo="Retenção do ISS"><select value={retencaoIss} onChange={(e) => setRetencaoIss(e.target.value)}><option value="1">Não retido</option><option value="2">Retido pelo tomador</option><option value="3">Retido pelo intermediário</option></select></Campo>
                  <Campo rotulo="Benefício municipal de ISS"><select value={beneficioIss} onChange={(e) => setBeneficioIss(e.target.value)}><option value="">Nenhum</option><option value="1">Isenção</option><option value="2">Redução da base</option></select></Campo>
                  <Valor rotulo="CBS sem redistribuição do ISS (%)" valor={cbsSemIss} mudar={setCbsSemIss} />
                  <Valor rotulo="IBS sem redistribuição do ISS (%)" valor={ibsSemIss} mudar={setIbsSemIss} />
                </div>
              </details>}
              {itens.length > 1 && <div className="form-actions"><Button type="button" variant="secondary" onClick={() => { simulacao.reset(); setItens(itens.filter((i) => i.id !== item.id)); }}><Trash2 size={15} aria-hidden /> Remover item {index + 1}</Button></div>}
              </fieldset>
            </section>
          );
        })}
        {erro && <Alert tone="error">{erro}</Alert>}
        {simulacao.isError && <Alert tone="error">{errorMessage(simulacao.error)}</Alert>}
        <div className="form-actions">
          {!nfseSimples && itens.length < 25 && <Button type="button" variant="secondary" disabled={simulacao.isPending} onClick={() => { simulacao.reset(); setItens([...itens, novoItem(++sequencia.current)]); }}><Plus size={16} aria-hidden /> Adicionar item</Button>}
          <Button type="submit" loading={simulacao.isPending}>Calcular tributos</Button>
        </div>
      </form>
      {simulacao.data && <Resultado resultado={simulacao.data} />}
      <Sheet open={lookup !== null} title={lookup ? CATALOGOS[lookup.tipo] : "Consultar código"} onClose={() => setLookup(null)} wide>
        {lookup && <Referencias key={lookup.tipo} tipo={lookup.tipo} data={data} documento={documento} selecionar={usarReferencia} />}
      </Sheet>
    </div>
  );
}
