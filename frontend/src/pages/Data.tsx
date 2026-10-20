import { useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Archive,
  CheckCircle2,
  FileJson,
  FileSpreadsheet,
  FileText,
  FileUp,
  History,
  Landmark,
  RotateCcw,
  Sheet as SheetIcon,
  Undo2,
} from "lucide-react";
import { Link, useSearchParams } from "react-router";

import { useCategories } from "../api/budget";
import { errorMessage } from "../api/client";
import {
  dataApi,
  download,
  exportQuery,
  readTextFile,
  type ColumnMapping,
  type ExportFilters,
  type ImportAnalysis,
  type LegacyPreview,
  type StatementPreview,
} from "../api/data";
import { hasCredit, useCards } from "../api/extras";
import { useAccounts } from "../api/money";
import { Badge, CategorySelect } from "../components/budget";
import { DateField } from "../components/DateField";
import { Tip } from "../components/help";
import { Alert, Button, PageHeader } from "../components/ui";
import { announce } from "../lib/announce";
import { addMonths, money, monthLabel, shortDate, thisMonth } from "../lib/format";

// ================================================================ importar

const ACCEPTED = [
  { icon: <Landmark size={18} />, name: "OFX", text: "Extrato da conta ou fatura do cartão. Formato recomendado: quase todo banco oferece." },
  { icon: <FileText size={18} />, name: "CSV", text: "Extrato exportado pelo banco ou planilha própria." },
  { icon: <FileSpreadsheet size={18} />, name: "Excel (.xlsx)", text: "Planilha com data, descrição e valor, em qualquer ordem." },
  { icon: <Archive size={18} />, name: "Backup do Meu Orçamento (.json)", text: "Restaura seus dados sem duplicar o que já existe." },
  { icon: <FileJson size={18} />, name: "App antigo (.json)", text: "Arquivo exportado pela versão anterior do Meu Orçamento." },
];
const STEPS = ["Arquivo", "Conferir campos", "Prévia", "Concluído"];
const FIELD_LABELS: { key: keyof ColumnMapping; label: string; tip: string }[] = [
  { key: "date", label: "Data", tip: "Data do lançamento ou da compra." },
  { key: "description", label: "Descrição", tip: "Nome do estabelecimento ou histórico do lançamento." },
  { key: "amount", label: "Valor", tip: "Valor com sinal: negativo para saídas e positivo para entradas." },
  { key: "credit", label: "Crédito (entradas)", tip: "Coluna só com as entradas." },
  { key: "debit", label: "Débito (saídas)", tip: "Coluna só com as saídas." },
];

function Steps({ current }: { current: number }) {
  return (
    <ol className="steps" aria-label="Etapas da importação">
      {STEPS.map((label, index) => (
        <li key={label} className={index === current ? "is-current" : index < current ? "is-done" : undefined} aria-current={index === current ? "step" : undefined}>
          <span className="steps__number">{index < current ? <CheckCircle2 size={16} aria-hidden /> : index + 1}</span>
          {label}
        </li>
      ))}
    </ol>
  );
}

function Dropzone({ onFile, busy }: { onFile: (file: File) => void; busy: boolean }) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  function drop(e: DragEvent) {
    e.preventDefault();
    setOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) onFile(file);
  }
  return (
    <div
      className={`dropzone ${over ? "is-over" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={drop}
    >
      <FileUp size={28} aria-hidden />
      <p className="dropzone__title">Arraste o arquivo para cá</p>
      <p className="muted small">ou</p>
      <Button type="button" loading={busy} onClick={() => input.current?.click()}>
        Escolher arquivo
      </Button>
      <input
        ref={input}
        type="file"
        hidden
        accept=".ofx,.qfx,.csv,.txt,.xlsx,.json,application/json,text/csv"
        data-testid="import-input"
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (file) onFile(file);
        }}
      />
      <p className="muted small">Até 5 MB. O formato é identificado pelo conteúdo do arquivo.</p>
    </div>
  );
}

function MappingStep({
  analysis,
  mapping,
  setMapping,
  kind,
  setKind,
  remember,
  setRemember,
}: {
  analysis: ImportAnalysis;
  mapping: ColumnMapping;
  setMapping: (m: ColumnMapping) => void;
  kind: "account" | "card";
  setKind: (k: "account" | "card") => void;
  remember: boolean;
  setRemember: (v: boolean) => void;
}) {
  const split = mapping.amount === null && (mapping.credit !== null || mapping.debit !== null);
  const [separate, setSeparate] = useState(split);
  const columns = analysis.columns ?? [];
  const used = new Set([mapping.date, mapping.description, mapping.amount, mapping.credit, mapping.debit].filter((v) => v !== null));
  const fields = FIELD_LABELS.filter((f) => (separate ? f.key !== "amount" : f.key !== "credit" && f.key !== "debit"));

  return (
    <div className="stack">
      <p style={{ margin: 0 }}>
        {analysis.mapping_source === "saved"
          ? "Modelo de arquivo reconhecido: usamos as colunas que você confirmou da última vez."
          : "Identificamos as colunas abaixo. Confira e corrija se necessário."}
      </p>
      <fieldset className="radios">
        <legend className="field-label">Este arquivo é</legend>
        <div className="segmented">
          <label>
            <input type="radio" name="statement-kind" checked={kind === "account"} onChange={() => setKind("account")} />
            Extrato da conta
          </label>
          <label>
            <input type="radio" name="statement-kind" checked={kind === "card"} onChange={() => setKind("card")} />
            Fatura de cartão
          </label>
        </div>
      </fieldset>
      <label className="check">
        <input
          type="checkbox"
          checked={separate}
          onChange={(e) => {
            setSeparate(e.target.checked);
            setMapping(e.target.checked ? { ...mapping, amount: null } : { ...mapping, credit: null, debit: null });
          }}
        />
        Entradas e saídas estão em colunas separadas (crédito e débito)
      </label>
      <div className="mapping-grid">
        {fields.map((f) => (
          <label key={f.key}>
            <span className="field-label">
              {f.label} <Tip>{f.tip}</Tip>
            </span>
            <select
              value={mapping[f.key] === null ? "" : String(mapping[f.key])}
              onChange={(e) => setMapping({ ...mapping, [f.key]: e.target.value === "" ? null : Number(e.target.value) })}
              required={f.key !== "description"}
            >
              <option value="">{f.key === "description" ? "Não usar" : "Escolha a coluna"}</option>
              {columns.map((name, index) => (
                <option key={index} value={index}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>
      {(analysis.sample ?? []).length > 0 && (
        <div className="table-wrap" tabIndex={0} role="region" aria-label="Primeiras linhas do arquivo">
          <table className="table table--compact">
            <thead>
              <tr>
                {columns.map((name, index) => (
                  <th key={index} className={used.has(index) ? "is-mapped" : undefined}>
                    {name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(analysis.sample ?? []).map((row, r) => (
                <tr key={r}>
                  {columns.map((_, index) => (
                    <td key={index} className={used.has(index) ? "is-mapped" : "muted"}>
                      {row[index] ?? ""}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {analysis.signature && (
        <label className="check">
          <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
          Lembrar estas colunas para arquivos com o mesmo modelo
        </label>
      )}
    </div>
  );
}

function LegacyReview({ data, onDone, onCancel }: { data: unknown; onDone: (text: string) => void; onCancel: () => void }) {
  const [month, setMonth] = useState(thisMonth());
  const [preview, setPreview] = useState<LegacyPreview | null>(null);
  const [skip, setSkip] = useState<Set<string>>(new Set());
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const queryClient = useQueryClient();

  const toggle = (key: string) =>
    setSkip((s) => {
      const next = new Set(s);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  const setRecurring = (kind: "incomes" | "expenses", index: number, value: boolean) =>
    setPreview((p) => {
      if (!p) return p;
      const list = [...p[kind]];
      list[index] = { ...list[index], recurring: value };
      return { ...p, [kind]: list };
    });

  async function load() {
    setError("");
    setBusy(true);
    try {
      setPreview(await dataApi.legacyPreview(month, data));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    if (!preview) return;
    setBusy(true);
    setError("");
    try {
      const result = await dataApi.legacyImport({
        month: preview.month,
        incomes: preview.incomes.filter((_, i) => !skip.has(`i${i}`)),
        expenses: preview.expenses.filter((_, i) => !skip.has(`e${i}`)),
        goals: skip.has("goals") ? [] : preview.goals,
        history: skip.has("history") ? [] : preview.history,
        reserve: skip.has("reserve") ? null : preview.reserve,
      });
      await queryClient.invalidateQueries({ queryKey: ["budget"] });
      onDone(
        `${result.incomes} receita(s), ${result.expenses} despesa(s), ${result.goals} meta(s), ` +
          `${result.history_months} mês(es) de histórico e ${result.investments} reserva importados.`,
      );
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (!preview)
    return (
      <div className="stack">
        <Alert tone="error">{error}</Alert>
        <p style={{ margin: 0 }}>Arquivo do app antigo reconhecido. Informe o mês a que os valores do arquivo se referem.</p>
        <div className="row row--end">
          <label className="month-picker">
            Mês dos dados
            <DateField month value={month} onChange={(v) => v && setMonth(v)} />
          </label>
          <Button type="button" variant="secondary" onClick={onCancel}>
            Cancelar
          </Button>
          <Button type="button" loading={busy} onClick={() => void load()}>
            Ver prévia
          </Button>
        </div>
      </div>
    );

  return (
    <div className="stack">
      <Alert tone="error">{error}</Alert>
      {preview.already_imported && <Alert tone="info">Um arquivo antigo já foi importado. Uma nova importação pode duplicar lançamentos.</Alert>}
      <p style={{ margin: 0 }}>
        Destino: <strong>{monthLabel(preview.month)}</strong>. Marque <em>todo mês</em> no que se repete (salário, aluguel, mensalidades).
      </p>
      {preview.incomes.length > 0 && (
        <div>
          <h3>Receitas</h3>
          <ul className="items">
            {preview.incomes.map((item, i) => (
              <li key={`i${i}`} className={`item ${skip.has(`i${i}`) ? "item--skipped" : ""}`}>
                <input type="checkbox" className="item__check" checked={!skip.has(`i${i}`)} onChange={() => toggle(`i${i}`)} aria-label={`Importar ${item.description}`} />
                <span className="item__main">
                  <span className="item__title">{item.description}</span>
                </span>
                <label className="check small">
                  <input type="checkbox" checked={item.recurring} onChange={(e) => setRecurring("incomes", i, e.target.checked)} />
                  todo mês
                </label>
                <span className="item__amount">{money(item.amount)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {preview.expenses.length > 0 && (
        <div>
          <h3>Despesas</h3>
          <ul className="items">
            {preview.expenses.map((item, i) => (
              <li key={`e${i}`} className={`item ${skip.has(`e${i}`) ? "item--skipped" : ""}`}>
                <input type="checkbox" className="item__check" checked={!skip.has(`e${i}`)} onChange={() => toggle(`e${i}`)} aria-label={`Importar ${item.description}`} />
                <span className="item__main">
                  <span className="item__title">{item.description}</span>
                  <span className="item__meta">
                    {item.category_name ?? "Sem categoria"}
                    {item.due_day && ` · dia ${item.due_day}`}
                    {item.paid && " · paga"}
                  </span>
                </span>
                {item.installment_total ? (
                  <Badge tone="accent">
                    {item.installment_current}/{item.installment_total}
                  </Badge>
                ) : (
                  <label className="check small">
                    <input type="checkbox" checked={item.recurring} onChange={(e) => setRecurring("expenses", i, e.target.checked)} />
                    todo mês
                  </label>
                )}
                <span className="item__amount">{money(item.amount)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="stack stack--tight">
        {preview.history.length > 0 && (
          <label className="check">
            <input type="checkbox" checked={!skip.has("history")} onChange={() => toggle("history")} />
            Histórico de {preview.history.length} mês(es) anterior(es), como totais de receitas e despesas
          </label>
        )}
        {preview.goals.length > 0 && (
          <label className="check">
            <input type="checkbox" checked={!skip.has("goals")} onChange={() => toggle("goals")} />
            {preview.goals.length} meta(s): {preview.goals.map((g) => g.name).join(", ")}
          </label>
        )}
        {preview.reserve && (
          <label className="check">
            <input type="checkbox" checked={!skip.has("reserve")} onChange={() => toggle("reserve")} />
            Reserva de emergência de {money(preview.reserve)} (vai para Investimentos)
          </label>
        )}
      </div>
      <div className="form-actions">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Cancelar
        </Button>
        <Button type="button" loading={busy} onClick={() => void save()}>
          Importar
        </Button>
      </div>
    </div>
  );
}

type Done = { text: string; batchId?: string };

function ImportWizard() {
  const queryClient = useQueryClient();
  const categories = useCategories();
  const accounts = useAccounts();
  const cards = useCards();
  const creditCards = (cards.data ?? []).map((c) => c.card).filter(hasCredit);
  const [step, setStep] = useState(0);
  const [file, setFile] = useState<File | null>(null);
  const [analysis, setAnalysis] = useState<ImportAnalysis | null>(null);
  const [legacyData, setLegacyData] = useState<unknown>(null);
  const [mapping, setMapping] = useState<ColumnMapping | null>(null);
  const [kind, setKind] = useState<"account" | "card">("account");
  const [remember, setRemember] = useState(true);
  const [preview, setPreview] = useState<StatementPreview | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [categoryOf, setCategoryOf] = useState<Record<string, string>>({});
  const [target, setTarget] = useState("");
  const [done, setDone] = useState<Done | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const batches = useQuery({ queryKey: ["import", "batches"], queryFn: dataApi.batches });

  function reset() {
    setStep(0);
    setFile(null);
    setAnalysis(null);
    setLegacyData(null);
    setMapping(null);
    setPreview(null);
    setDone(null);
    setError("");
    setTarget("");
  }

  async function run<T>(fn: () => Promise<T>): Promise<T | undefined> {
    setError("");
    setBusy(true);
    try {
      return await fn();
    } catch (err) {
      setError(errorMessage(err));
      return undefined;
    } finally {
      setBusy(false);
    }
  }

  async function loadPreview(target: File, a: ImportAnalysis, m: ColumnMapping | null, k: "account" | "card") {
    const invert = a.format === "ofx" ? false : k === "card";
    const result = await run(() => dataApi.preview(target, m ?? undefined, invert));
    if (!result) return;
    setPreview(result);
    // Já importados e pagamentos de fatura (as compras do cartão já estão no app) vêm desmarcados.
    setSelected(new Set(result.transactions.filter((t) => !t.duplicate && !t.card_payment).map((t) => t.ref)));
    setCategoryOf(Object.fromEntries(result.transactions.map((t) => [t.ref, t.category_id ?? ""])));
    if (k === "card" && creditCards.length === 1) setTarget(`card:${creditCards[0].id}`);
    setStep(2);
  }

  async function onFile(chosen: File) {
    reset();
    setFile(chosen);
    const a = await run(() => dataApi.analyze(chosen));
    if (!a) return;
    setAnalysis(a);
    const k = a.kind === "card" ? "card" : "account";
    setKind(k);
    if (a.kind === "legacy") {
      setLegacyData(JSON.parse(await readTextFile(chosen)));
      setStep(1);
    } else if (a.kind === "backup") {
      setStep(1);
    } else if (a.format === "ofx") {
      await loadPreview(chosen, a, null, k);
    } else {
      setMapping(a.mapping ?? null);
      setStep(1);
    }
  }

  async function restore() {
    if (!file) return;
    const counts = await run(() => dataApi.restore(file));
    if (!counts) return;
    await queryClient.invalidateQueries();
    const total = Object.values(counts).reduce((a, b) => a + b, 0);
    setDone({
      text:
        total === 0
          ? "Nada a restaurar: todos os registros do backup já existem nesta conta."
          : `Restaurados: ${counts.incomes} receita(s), ${counts.expenses} despesa(s), ${counts.goals} meta(s), ${counts.investments} investimento(s), ${counts.categories} categoria(s), ${counts.cards} cartão(ões) e ${counts.accounts} conta(s).`,
    });
    setStep(3);
  }

  async function commit() {
    if (!preview || !file || !analysis) return;
    const chosen = preview.transactions
      .filter((t) => selected.has(t.ref))
      .map(({ duplicate: _d, card_payment: _c, ...t }) => ({ ...t, category_id: t.kind === "expense" ? categoryOf[t.ref] || null : null }));
    const [type, id] = target.split(":");
    const result = await run(() =>
      dataApi.commit({
        transactions: chosen,
        filename: file.name,
        file_format: preview.format,
        account_id: type === "account" ? id : null,
        card_id: type === "card" ? id : null,
        save_mapping: remember && analysis.signature && mapping ? { signature: analysis.signature, mapping } : null,
      }),
    );
    if (!result) return;
    await queryClient.invalidateQueries({ queryKey: ["budget"] });
    await queryClient.invalidateQueries({ queryKey: ["import"] });
    announce("Importação concluída");
    setDone({
      text: `${result.created} lançamento(s) importado(s)${result.skipped ? `; ${result.skipped} já existiam e foram ignorados` : ""}.`,
      batchId: result.batch_id,
    });
    setStep(3);
  }

  async function undo(id: string) {
    const result = await run(() => dataApi.undo(id));
    if (!result) return;
    await queryClient.invalidateQueries({ queryKey: ["budget"] });
    await queryClient.invalidateQueries({ queryKey: ["import"] });
    announce(`${result.removed} lançamento(s) removido(s)`);
    if (done?.batchId === id) setDone({ text: `Importação desfeita: ${result.removed} lançamento(s) removido(s).` });
  }

  const items = preview?.transactions ?? [];
  const chosen = items.filter((t) => selected.has(t.ref));
  const duplicates = items.filter((t) => t.duplicate).length;
  const toggle = (ref: string) =>
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(ref)) next.delete(ref);
      else next.add(ref);
      return next;
    });
  const mappingReady =
    mapping !== null && mapping.date !== null && (mapping.amount !== null || (mapping.credit !== null && mapping.debit !== null));

  return (
    <div className="stack" style={{ gap: 20 }}>
      <section className="card stack">
        <div className="section-header">
          <h2>Importar dados</h2>
        </div>
        <Steps current={step} />
        <Alert tone="error">{error}</Alert>

        {step === 0 && (
          <div className="import-start">
            <Dropzone onFile={(f) => void onFile(f)} busy={busy} />
            <div className="stack stack--tight">
              <h3 style={{ margin: 0 }}>Arquivos aceitos</h3>
              <ul className="accepted">
                {ACCEPTED.map((a) => (
                  <li key={a.name}>
                    <span className="accepted__icon" aria-hidden>
                      {a.icon}
                    </span>
                    <span>
                      <strong>{a.name}</strong>
                      <span className="muted small">{a.text}</span>
                    </span>
                  </li>
                ))}
              </ul>
              <p className="muted small" style={{ margin: 0 }}>
                Extrato em PDF não é aceito: a leitura de PDF erra valores com facilidade. No app ou site do banco, use “exportar extrato” em OFX
                ou CSV.
              </p>
            </div>
          </div>
        )}

        {step === 1 && analysis?.kind === "legacy" && (
          <LegacyReview
            data={legacyData}
            onCancel={reset}
            onDone={(text) => {
              setDone({ text });
              setStep(3);
            }}
          />
        )}

        {step === 1 && analysis?.kind === "backup" && (
          <div className="stack">
            <p style={{ margin: 0 }}>
              Backup do Meu Orçamento reconhecido em <strong>{file?.name}</strong>. A restauração recria o que não existe nesta conta e não duplica o
              que já existe.
            </p>
            <ul className="backup-summary">
              {Object.entries(analysis.summary ?? {}).map(([key, value]) => (
                <li key={key}>
                  <strong>{value}</strong> {BACKUP_LABELS[key] ?? key}
                </li>
              ))}
            </ul>
            <div className="form-actions">
              <Button type="button" variant="secondary" onClick={reset}>
                Cancelar
              </Button>
              <Button type="button" loading={busy} onClick={() => void restore()}>
                <RotateCcw size={16} /> Restaurar backup
              </Button>
            </div>
          </div>
        )}

        {step === 1 && analysis && mapping && (analysis.format === "csv" || analysis.format === "xlsx") && (
          <div className="stack">
            <MappingStep
              analysis={analysis}
              mapping={mapping}
              setMapping={setMapping}
              kind={kind}
              setKind={setKind}
              remember={remember}
              setRemember={setRemember}
            />
            <div className="form-actions">
              <Button type="button" variant="secondary" onClick={reset}>
                Cancelar
              </Button>
              <Button type="button" loading={busy} disabled={!mappingReady} onClick={() => file && void loadPreview(file, analysis, mapping, kind)}>
                Continuar
              </Button>
            </div>
          </div>
        )}

        {step === 2 && preview && (
          <div className="stack">
            <p className="import-summary" style={{ margin: 0 }}>
              <strong>{items.length} lançamento(s)</strong>
              {duplicates > 0 && ` · ${duplicates} já importado(s), desmarcado(s)`}
              {preview.period && ` · período ${shortDate(preview.period.start)} a ${shortDate(preview.period.end)}`}
              {" · "}
              {chosen.length} selecionado(s)
            </p>
            <label className="narrow import-target">
              <span className="field-label">
                Destino <Tip>Conta de onde as saídas saíram ou cartão da fatura. Na fatura, cada compra vai para a fatura certa pelo dia da compra.</Tip>
              </span>
              <select value={target} onChange={(e) => setTarget(e.target.value)}>
                <option value="">Sem conta vinculada</option>
                {(accounts.data ?? []).map((b) => (
                  <option key={b.account.id} value={`account:${b.account.id}`}>
                    Conta: {b.account.name}
                  </option>
                ))}
                {creditCards.map((c) => (
                  <option key={c.id} value={`card:${c.id}`}>
                    Fatura do cartão: {c.name}
                  </option>
                ))}
              </select>
            </label>
            <div className="table-wrap" tabIndex={0} role="region" aria-label="Lançamentos encontrados no arquivo">
              <table className="table table--compact">
                <thead>
                  <tr>
                    <th>
                      <input
                        type="checkbox"
                        aria-label="Selecionar todos"
                        checked={chosen.length === items.length}
                        onChange={(e) => setSelected(new Set(e.target.checked ? items.map((t) => t.ref) : []))}
                      />
                    </th>
                    <th>Data</th>
                    <th>Descrição</th>
                    <th>Categoria</th>
                    <th className="num">Valor</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((t) => (
                    <tr key={t.ref} className={selected.has(t.ref) ? undefined : "muted"}>
                      <td>
                        <input type="checkbox" checked={selected.has(t.ref)} onChange={() => toggle(t.ref)} aria-label={`Importar ${t.description}`} />
                      </td>
                      <td>{shortDate(t.date)}</td>
                      <td className="wrap">
                        {t.description} {t.duplicate && <Badge>já importado</Badge>}
                        {t.card_payment && <Badge>pagamento de fatura</Badge>}
                      </td>
                      <td>
                        {t.kind === "expense" ? (
                          <CategorySelect
                            label={`Categoria de ${t.description}`}
                            categories={categories.data ?? []}
                            value={categoryOf[t.ref] ?? ""}
                            onChange={(v) => setCategoryOf((c) => ({ ...c, [t.ref]: v }))}
                          />
                        ) : (
                          <span className="muted">Receita</span>
                        )}
                      </td>
                      <td className={`num ${t.kind === "income" ? "tone--ok" : ""}`}>
                        {t.kind === "income" ? "+" : "−"}
                        {money(t.amount)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="form-actions">
              <Button type="button" variant="secondary" onClick={() => (analysis?.format === "ofx" ? reset() : setStep(1))}>
                Voltar
              </Button>
              <Button type="button" disabled={chosen.length === 0} loading={busy} onClick={() => void commit()}>
                Importar {chosen.length} lançamento(s)
              </Button>
            </div>
          </div>
        )}

        {step === 3 && done && (
          <div className="stack">
            <Alert tone="success">{done.text}</Alert>
            <p className="muted small" style={{ margin: 0 }}>
              Despesas importadas de extrato ficam em <Link to="/revisar">Para revisar</Link> até a conferência da categoria.
            </p>
            <div className="form-actions form-actions--split">
              {done.batchId && (
                <Button type="button" variant="secondary" loading={busy} onClick={() => void undo(done.batchId!)}>
                  <Undo2 size={16} /> Desfazer esta importação
                </Button>
              )}
              <Button type="button" onClick={reset}>
                Importar outro arquivo
              </Button>
            </div>
          </div>
        )}
      </section>

      {(batches.data ?? []).length > 0 && (
        <section className="card stack">
          <h2>
            <History size={18} aria-hidden /> Importações recentes
          </h2>
          <ul className="items">
            {(batches.data ?? []).map((b) => (
              <li key={b.id} className="item">
                <span className="item__main">
                  <span className="item__title">{b.filename}</span>
                  <span className="item__meta">
                    {new Date(b.created_at).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })} · {b.count} lançamento(s) ·{" "}
                    {b.file_format.toUpperCase()}
                    {b.undone_at && " · desfeita"}
                  </span>
                </span>
                {!b.undone_at && b.file_format !== "backup" && (
                  <Button type="button" variant="secondary" onClick={() => void undo(b.id)}>
                    <Undo2 size={16} /> Desfazer
                  </Button>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

const BACKUP_LABELS: Record<string, string> = {
  accounts: "conta(s)",
  categories: "categoria(s)",
  cards: "cartão(ões)",
  recurring: "recorrência(s)",
  incomes: "receita(s)",
  expenses: "despesa(s)",
  goals: "meta(s)",
  investments: "investimento(s)",
  loans: "financiamento(s)",
  other_debts: "outra(s) dívida(s)",
};

// ================================================================ exportar

type Preset = "month" | "3m" | "6m" | "12m" | "year" | "custom";
const PRESETS: [Preset, string][] = [
  ["month", "Este mês"],
  ["3m", "3 meses"],
  ["6m", "6 meses"],
  ["12m", "12 meses"],
  ["year", "Este ano"],
  ["custom", "Escolher"],
];

function presetRange(preset: Preset): [string, string] {
  const now = thisMonth();
  if (preset === "month") return [now, now];
  if (preset === "3m") return [addMonths(now, -2), now];
  if (preset === "6m") return [addMonths(now, -5), now];
  if (preset === "year") return [`${now.slice(0, 4)}-01`, now];
  return [addMonths(now, -11), now];
}

function ExportPanel() {
  const categories = useCategories();
  const accounts = useAccounts();
  const cards = useCards();
  const [preset, setPreset] = useState<Preset>("12m");
  const [range, setRange] = useState<[string, string]>(presetRange("12m"));
  const [kind, setKind] = useState<ExportFilters["kind"]>("all");
  const [cats, setCats] = useState<string[]>([]);
  const [places, setPlaces] = useState<string[]>([]);
  const [reportMonth, setReportMonth] = useState(thisMonth());
  const [year, setYear] = useState(String(new Date().getFullYear()));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  const filters: ExportFilters = useMemo(
    () => ({
      start: range[0],
      end: range[1],
      kind,
      categories: cats,
      places: {
        accounts: places.filter((p) => p.startsWith("a:")).map((p) => p.slice(2)),
        cards: places.filter((p) => p.startsWith("c:")).map((p) => p.slice(2)),
      },
    }),
    [range, kind, cats, places],
  );
  const count = useQuery({ queryKey: ["export", "count", exportQuery(filters)], queryFn: () => dataApi.exportCount(filters) });

  useEffect(() => {
    if (preset !== "custom") setRange(presetRange(preset));
  }, [preset]);

  async function get(key: string, path: string, name: string) {
    setError("");
    setBusy(key);
    try {
      await download(path, name);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy("");
    }
  }

  const toggleIn = (list: string[], set: (v: string[]) => void, value: string) =>
    set(list.includes(value) ? list.filter((v) => v !== value) : [...list, value]);
  const placeOptions = [
    ...(accounts.data ?? []).map((b) => ({ id: `a:${b.account.id}`, name: b.account.name })),
    ...(cards.data ?? []).map((c) => ({ id: `c:${c.card.id}`, name: c.card.name })),
  ];
  const years = Array.from({ length: 6 }, (_, i) => String(new Date().getFullYear() - i));
  const n = count.data?.count;

  return (
    <div className="stack" style={{ gap: 20 }}>
      <Alert tone="error">{error}</Alert>
      <section className="card stack">
        <div className="section-header">
          <h2>Lançamentos</h2>
          <span className="muted small" aria-live="polite">
            {n === undefined ? "Contando…" : `${n} lançamento(s) no recorte`}
          </span>
        </div>
        <fieldset className="radios">
          <legend className="field-label">Período</legend>
          <div className="chips" role="group" aria-label="Período">
            {PRESETS.map(([value, label]) => (
              <button key={value} type="button" className={`chip-btn ${preset === value ? "is-active" : ""}`} aria-pressed={preset === value} onClick={() => setPreset(value)}>
                {label}
              </button>
            ))}
          </div>
          {preset === "custom" && (
            <div className="row row--end" style={{ marginTop: 8 }}>
              <label className="month-picker">
                De
                <DateField month value={range[0]} onChange={(v) => v && setRange([v, range[1]])} />
              </label>
              <label className="month-picker">
                Até
                <DateField month value={range[1]} min={range[0]} onChange={(v) => v && setRange([range[0], v])} />
              </label>
            </div>
          )}
          <p className="muted small" style={{ margin: "6px 0 0" }}>
            {monthLabel(range[0])} a {monthLabel(range[1])}
          </p>
        </fieldset>
        <fieldset className="radios">
          <legend className="field-label">Conteúdo</legend>
          <div className="segmented">
            {(
              [
                ["all", "Receitas e despesas"],
                ["expense", "Só despesas"],
                ["income", "Só receitas"],
              ] as const
            ).map(([value, label]) => (
              <label key={value}>
                <input type="radio" name="export-kind" checked={kind === value} onChange={() => setKind(value)} />
                {label}
              </label>
            ))}
          </div>
        </fieldset>
        {placeOptions.length > 0 && (
          <fieldset className="radios">
            <legend className="field-label">Contas e cartões</legend>
            <div className="chips" role="group" aria-label="Contas e cartões">
              {placeOptions.map((p) => (
                <button key={p.id} type="button" className={`chip-btn ${places.includes(p.id) ? "is-active" : ""}`} aria-pressed={places.includes(p.id)} onClick={() => toggleIn(places, setPlaces, p.id)}>
                  {p.name}
                </button>
              ))}
            </div>
            <p className="muted small" style={{ margin: "6px 0 0" }}>{places.length ? `${places.length} selecionado(s)` : "Todos"}</p>
          </fieldset>
        )}
        {kind !== "income" && (
          <fieldset className="radios">
            <legend className="field-label">Categorias</legend>
            <div className="chips" role="group" aria-label="Categorias">
              {(categories.data ?? []).map((c) => (
                <button key={c.id} type="button" className={`chip-btn ${cats.includes(c.id) ? "is-active" : ""}`} aria-pressed={cats.includes(c.id)} onClick={() => toggleIn(cats, setCats, c.id)}>
                  {c.name}
                </button>
              ))}
            </div>
            <p className="muted small" style={{ margin: "6px 0 0" }}>{cats.length ? `${cats.length} selecionada(s)` : "Todas"}</p>
          </fieldset>
        )}
        <div className="export-grid">
          <div className="export-card">
            <SheetIcon size={20} aria-hidden />
            <strong>Planilha Excel</strong>
            <p className="muted small">Para analisar: abas de lançamentos, resumo mensal e total por categoria, já formatadas.</p>
            <Button type="button" variant="secondary" disabled={n === 0} loading={busy === "xlsx"} onClick={() => void get("xlsx", `/export/transactions?${exportQuery(filters)}&format=xlsx`, "lancamentos.xlsx")}>
              Baixar Excel
            </Button>
          </div>
          <div className="export-card">
            <FileText size={20} aria-hidden />
            <strong>CSV</strong>
            <p className="muted small">Para levar a outro aplicativo ou enviar ao contador. Abre no Excel e no Google Planilhas.</p>
            <Button type="button" variant="secondary" disabled={n === 0} loading={busy === "csv"} onClick={() => void get("csv", `/export/transactions?${exportQuery(filters)}&format=csv`, "lancamentos.csv")}>
              Baixar CSV
            </Button>
          </div>
        </div>
      </section>

      <section className="card stack">
        <h2>Relatórios em PDF</h2>
        <p className="muted small" style={{ margin: 0 }}>
          Os relatórios abrem prontos para imprimir. Na janela de impressão, escolha “Salvar como PDF”.
        </p>
        <div className="export-grid">
          <div className="export-card">
            <FileText size={20} aria-hidden />
            <strong>Relatório do mês</strong>
            <p className="muted small">Resultado, despesas por categoria, metas e lançamentos do mês.</p>
            <label className="month-picker">
              Mês
              <DateField month value={reportMonth} onChange={(v) => v && setReportMonth(v)} />
            </label>
            <Link className="btn btn--secondary" to={`/relatorio/${reportMonth}`}>
              Abrir relatório do mês
            </Link>
          </div>
          <div className="export-card">
            <FileText size={20} aria-hidden />
            <strong>Resumo anual</strong>
            <p className="muted small">Receitas, despesas por categoria, mês a mês e patrimônio. Útil na conferência do Imposto de Renda; não é documento fiscal.</p>
            <label>
              Ano
              <select value={year} onChange={(e) => setYear(e.target.value)}>
                {years.map((y) => (
                  <option key={y}>{y}</option>
                ))}
              </select>
            </label>
            <Link className="btn btn--secondary" to={`/relatorio/ano/${year}`}>
              Abrir resumo anual
            </Link>
          </div>
        </div>
      </section>

      <section className="card stack">
        <h2>Backup completo</h2>
        <p className="muted" style={{ margin: 0 }}>
          Todos os seus dados (contas, cartões, categorias, lançamentos, recorrências, metas, investimentos e solicitações) em um arquivo JSON.
          Use para guardar uma cópia ou restaurar em “Importar dados”. É também o seu direito de portabilidade previsto na LGPD.
        </p>
        <p className="muted small" style={{ margin: 0 }}>Guarde em local seguro: o arquivo contém toda a sua vida financeira.</p>
        <div>
          <Button type="button" variant="secondary" loading={busy === "backup"} onClick={() => void get("backup", "/export/backup", "meu-orcamento-backup.json")}>
            <Archive size={16} /> Baixar backup
          </Button>
        </div>
      </section>
    </div>
  );
}

export default function DataPage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("aba") === "exportar" ? "exportar" : "importar";
  return (
    <>
      <PageHeader
        title="Importar e exportar"
        subtitle="Traga extratos, planilhas e backups em uma única importação; leve seus dados em planilha, relatório ou backup."
      />
      <nav className="page-tabs no-print" aria-label="Importar ou exportar" style={{ marginBottom: 20 }}>
        {(
          [
            ["importar", "Importar"],
            ["exportar", "Exportar"],
          ] as const
        ).map(([key, label]) => (
          <a
            key={key}
            href={`?aba=${key}`}
            aria-current={tab === key ? "page" : undefined}
            onClick={(e) => {
              e.preventDefault();
              setParams({ aba: key }, { replace: true });
            }}
          >
            {label}
          </a>
        ))}
      </nav>
      {tab === "importar" ? <ImportWizard /> : <ExportPanel />}
    </>
  );
}
