import { useRef, useState, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { Calculator, Download, FileSearch } from "lucide-react";

import { errorMessage } from "../../api/client";
import { gerarDanfse, MAX_XML_BYTES } from "../../api/rtc";
import { todayISO } from "../../lib/format";
import { Alert, Button } from "../ui";
import { CATALOGOS, Referencias, type CatalogoFiscal } from "./Referencias";
import { SimuladorRtc } from "./Simulador";

const FERRAMENTAS = [
  { id: "simular", label: "Simular tributos", Icon: Calculator },
  { id: "referencias", label: "Consultar tabelas", Icon: FileSearch },
  { id: "danfse", label: "Gerar DANFSe", Icon: Download },
] as const;

function Tabelas() {
  const [tipo, setTipo] = useState<CatalogoFiscal>("ncm");
  const [data, setData] = useState(todayISO);
  return (
    <section className="card stack" aria-label="Tabelas da Receita Federal">
      <div className="grid-2">
        <label className="field">
          <span className="field-label">Tabela fiscal</span>
          <select value={tipo} onChange={(e) => setTipo(e.target.value as CatalogoFiscal)}>
            {Object.entries(CATALOGOS).map(([key, label]) => <option value={key} key={key}>{label}</option>)}
          </select>
        </label>
        <label className="field">
          <span className="field-label">Data de vigência</span>
          <input type="date" value={data} onChange={(e) => setData(e.target.value)} />
        </label>
      </div>
      <Referencias key={`${tipo}-${data}`} tipo={tipo} data={data} />
    </section>
  );
}

function Danfse() {
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [erro, setErro] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const pdf = useMutation({ mutationFn: gerarDanfse, onSuccess: () => {
    setArquivo(null);
    if (input.current) input.current.value = "";
  } });

  function enviar(event: FormEvent) {
    event.preventDefault();
    if (arquivo && !pdf.isPending) pdf.mutate(arquivo);
  }

  return (
    <form className="card inline-form stack" onSubmit={enviar} aria-label="Gerador de DANFSe">
      <h3>PDF da nota de serviço</h3>
      <p className="muted">Selecione o XML de uma NFS-e já emitida. O arquivo será usado apenas para gerar o PDF.</p>
      <label className="field">
        <span className="field-label">XML da NFS-e</span>
        <input ref={input} type="file" accept=".xml,application/xml,text/xml" disabled={pdf.isPending} onChange={(e) => {
          const novo = e.target.files?.[0] ?? null;
          pdf.reset();
          if (novo && (!novo.size || novo.size > MAX_XML_BYTES || !novo.name.toLowerCase().endsWith(".xml"))) {
            setErro("Selecione um arquivo XML com conteúdo e até 5 MB.");
            setArquivo(null);
            e.target.value = "";
            return;
          }
          setErro("");
          setArquivo(novo);
        }} />
      </label>
      {(erro || pdf.isError) && <Alert tone="error">{erro || errorMessage(pdf.error)}</Alert>}
      {pdf.isSuccess && <Alert tone="success">PDF gerado. Confira os downloads do navegador.</Alert>}
      <div className="form-actions"><Button type="submit" disabled={!arquivo} loading={pdf.isPending}><Download size={16} aria-hidden /> Baixar DANFSe</Button></div>
    </form>
  );
}

export default function ReformaTributaria() {
  const [aba, setAba] = useState<(typeof FERRAMENTAS)[number]["id"]>("simular");
  return (
    <div className="stack rtc">
      <div className="chips" role="group" aria-label="Ferramentas da Reforma Tributária">
        {FERRAMENTAS.map(({ id, label, Icon }) => <button key={id} type="button" className="chip-btn" aria-pressed={aba === id} onClick={() => setAba(id)}><Icon size={16} aria-hidden /> {label}</button>)}
      </div>
      {aba === "simular" && <SimuladorRtc />}
      {aba === "referencias" && <Tabelas />}
      {aba === "danfse" && <Danfse />}
    </div>
  );
}
