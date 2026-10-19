import { useState, type ChangeEvent } from "react";
import { Link } from "react-router";

import { useBudgetMutation, useCategories } from "../api/budget";
import { errorMessage } from "../api/client";
import {
  dataApi,
  download,
  readTextFile,
  type LegacyPreview,
  type StatementPreview,
} from "../api/data";
import { Badge, CategorySelect } from "../components/budget";
import { Alert, Button, PageHeader } from "../components/ui";
import { addMonths, money, monthLabel, shortDate, thisMonth } from "../lib/format";

// ---------------------------------------------------------------- app antigo

function LegacyImport() {
  const [month, setMonth] = useState(thisMonth());
  const [preview, setPreview] = useState<LegacyPreview | null>(null);
  const [skip, setSkip] = useState<Set<string>>(new Set());
  const [error, setError] = useState("");
  const [done, setDone] = useState("");
  const [loading, setLoading] = useState(false);

  async function onFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setError("");
    setDone("");
    setLoading(true);
    try {
      let data: unknown;
      try {
        data = JSON.parse(await readTextFile(file));
      } catch {
        throw new Error("O arquivo não é um JSON válido. Use o arquivo exportado pelo app antigo (botão JSON).");
      }
      setPreview(await dataApi.legacyPreview(month, data));
      setSkip(new Set());
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  const toggle = (key: string) =>
    setSkip((s) => {
      const next = new Set(s);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  const run = useBudgetMutation(async () => {
    if (!preview) return;
    const result = await dataApi.legacyImport({
      month: preview.month,
      incomes: preview.incomes.filter((_, i) => !skip.has(`i${i}`)),
      expenses: preview.expenses.filter((_, i) => !skip.has(`e${i}`)),
      goals: skip.has("goals") ? [] : preview.goals,
      history: skip.has("history") ? [] : preview.history,
      reserve: skip.has("reserve") ? null : preview.reserve,
    });
    setDone(
      `Importado: ${result.incomes} renda(s), ${result.expenses} conta(s), ${result.goals} meta(s), ` +
        `${result.history_months} mês(es) de histórico e ${result.investments} reserva.`,
    );
    setPreview(null);
  });

  const setRecurring = (kind: "incomes" | "expenses", index: number, value: boolean) =>
    setPreview((p) => {
      if (!p) return p;
      const list = [...p[kind]];
      list[index] = { ...list[index], recurring: value };
      return { ...p, [kind]: list };
    });

  return (
    <section className="card stack">
      <h2>Importar do app antigo</h2>
      <p className="muted small">
        Use o arquivo <code>.json</code> exportado pelo Meu Orçamento antigo. Antes de gravar, você revisa tudo. Seu
        perfil (nome, idade) não é importado.
      </p>
      <Alert tone="error">{error}</Alert>
      <Alert tone="success">{done}</Alert>
      {!preview && (
        <div className="row row--end">
          <label className="month-picker">
            Os dados do arquivo são de qual mês?
            <input type="month" value={month} onChange={(e) => e.target.value && setMonth(e.target.value)} />
          </label>
          <label className={`btn btn--primary ${loading ? "is-loading" : ""}`}>
            {loading ? "Lendo…" : "Escolher arquivo .json"}
            <input type="file" accept=".json,application/json" onChange={onFile} hidden />
          </label>
        </div>
      )}

      {preview && (
        <div className="stack">
          {preview.already_imported && (
            <Alert tone="info">Você já importou um arquivo antigo antes. Importar de novo pode duplicar lançamentos.</Alert>
          )}
          <p>
            Destino: <strong>{monthLabel(preview.month)}</strong>. Marque <em>todo mês</em> no que se repete
            (salário, aluguel, mensalidades).
          </p>

          {preview.incomes.length > 0 && (
            <div>
              <h3>Rendas</h3>
              <ul className="items">
                {preview.incomes.map((item, i) => (
                  <li key={`i${i}`} className={`item ${skip.has(`i${i}`) ? "item--skipped" : ""}`}>
                    <input type="checkbox" className="item__check" checked={!skip.has(`i${i}`)} onChange={() => toggle(`i${i}`)} aria-label="Importar" />
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
              <h3>Contas</h3>
              <ul className="items">
                {preview.expenses.map((item, i) => (
                  <li key={`e${i}`} className={`item ${skip.has(`e${i}`) ? "item--skipped" : ""}`}>
                    <input type="checkbox" className="item__check" checked={!skip.has(`e${i}`)} onChange={() => toggle(`e${i}`)} aria-label="Importar" />
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
                Histórico de {preview.history.length} mês(es) anterior(es), como totais de renda e contas
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

          <div className="row">
            <Button type="button" variant="secondary" onClick={() => setPreview(null)}>
              Cancelar
            </Button>
            <Button
              type="button"
              loading={run.isPending}
              onClick={() => run.mutateAsync(undefined).catch((err) => setError(errorMessage(err)))}
            >
              Importar
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------- extrato

function StatementImport() {
  const categories = useCategories();
  const [preview, setPreview] = useState<StatementPreview | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [categoryOf, setCategoryOf] = useState<Record<string, string>>({});
  const [invert, setInvert] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [done, setDone] = useState("");
  const [loading, setLoading] = useState(false);

  async function load(target: File, invertSigns: boolean) {
    setError("");
    setDone("");
    setLoading(true);
    try {
      const result = await dataApi.statementPreview(target.name, await readTextFile(target), invertSigns);
      setPreview(result);
      // Já importados e pagamentos de fatura (as compras do cartão já estão no app) vêm desmarcados.
      setSelected(new Set(result.transactions.filter((t) => !t.duplicate && !t.card_payment).map((t) => t.ref)));
      setCategoryOf(Object.fromEntries(result.transactions.map((t) => [t.ref, t.category_id ?? ""])));
    } catch (err) {
      setPreview(null);
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  async function onFile(event: ChangeEvent<HTMLInputElement>) {
    const target = event.target.files?.[0];
    event.target.value = "";
    if (!target) return;
    setFile(target);
    await load(target, invert);
  }

  const run = useBudgetMutation(async () => {
    if (!preview) return;
    const chosen = preview.transactions
      .filter((t) => selected.has(t.ref))
      .map(({ duplicate: _duplicate, card_payment: _card, ...t }) => ({
        ...t,
        category_id: t.kind === "expense" ? categoryOf[t.ref] || null : null,
      }));
    const result = await dataApi.statementImport(chosen);
    setDone(
      `${result.created} lançamento(s) importado(s)` +
        (result.skipped ? `, ${result.skipped} já existiam e foram ignorados.` : "."),
    );
    setPreview(null);
    setFile(null);
  });

  const items = preview?.transactions ?? [];
  const chosen = items.filter((t) => selected.has(t.ref));
  const toggle = (ref: string) =>
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(ref)) next.delete(ref);
      else next.add(ref);
      return next;
    });

  return (
    <section className="card stack">
      <h2>Importar extrato bancário</h2>
      <p className="muted small">
        Aceita <strong>OFX</strong> (recomendado, quase todo banco oferece em "exportar extrato") e{" "}
        <strong>CSV</strong>. As saídas viram contas pagas e as entradas viram renda. Lançamentos já importados são
        reconhecidos e ficam desmarcados.
      </p>
      <Alert tone="error">{error}</Alert>
      <Alert tone="success">{done}</Alert>
      <div className="row row--end">
        <label className="check">
          <input
            type="checkbox"
            checked={invert}
            onChange={(e) => {
              setInvert(e.target.checked);
              if (file) load(file, e.target.checked);
            }}
          />
          É fatura de cartão (compras aparecem como valores positivos)
        </label>
        <label className={`btn btn--primary ${loading ? "is-loading" : ""}`}>
          {loading ? "Lendo…" : "Escolher arquivo"}
          <input type="file" accept=".ofx,.qfx,.csv,.txt" onChange={onFile} hidden />
        </label>
      </div>

      {preview && (
        <div className="stack">
          <p className="small">
            {items.length} lançamento(s) em <strong>{file?.name}</strong> ({preview.format.toUpperCase()}).{" "}
            {chosen.length} selecionado(s).
          </p>
          <div className="table-wrap" tabIndex={0} role="region" aria-label="Lançamentos encontrados no extrato">
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
                      <input type="checkbox" checked={selected.has(t.ref)} onChange={() => toggle(t.ref)} aria-label="Importar" />
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
                        <span className="muted">Renda</span>
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
          <div className="row">
            <Button type="button" variant="secondary" onClick={() => setPreview(null)}>
              Cancelar
            </Button>
            <Button
              type="button"
              disabled={chosen.length === 0}
              loading={run.isPending}
              onClick={() => run.mutateAsync(undefined).catch((err) => setError(errorMessage(err)))}
            >
              Importar {chosen.length} lançamento(s)
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------- exportar

function Export() {
  const [start, setStart] = useState(addMonths(thisMonth(), -11));
  const [end, setEnd] = useState(thisMonth());
  const [reportMonth, setReportMonth] = useState(thisMonth());
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  async function get(kind: string, path: string, name: string) {
    setError("");
    setBusy(kind);
    try {
      await download(path, name);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy("");
    }
  }

  return (
    <section className="card stack">
      <h2>Exportar</h2>
      <Alert tone="error">{error}</Alert>
      <div className="stack stack--tight">
        <h3>Lançamentos de um período</h3>
        <div className="row row--end">
          <label className="month-picker">
            De
            <input type="month" value={start} onChange={(e) => e.target.value && setStart(e.target.value)} />
          </label>
          <label className="month-picker">
            Até
            <input type="month" value={end} onChange={(e) => e.target.value && setEnd(e.target.value)} />
          </label>
          <Button
            type="button"
            variant="secondary"
            loading={busy === "csv"}
            onClick={() => get("csv", `/export/transactions?start=${start}&end=${end}&format=csv`, "lancamentos.csv")}
          >
            CSV
          </Button>
          <Button
            type="button"
            variant="secondary"
            loading={busy === "xlsx"}
            onClick={() => get("xlsx", `/export/transactions?start=${start}&end=${end}&format=xlsx`, "lancamentos.xlsx")}
          >
            Excel
          </Button>
        </div>
      </div>
      <div className="stack stack--tight">
        <h3>Relatório do mês (PDF)</h3>
        <div className="row row--end">
          <label className="month-picker">
            Mês
            <input type="month" value={reportMonth} onChange={(e) => e.target.value && setReportMonth(e.target.value)} />
          </label>
          <Link className="btn btn--secondary" to={`/relatorio/${reportMonth}`}>
            Abrir relatório
          </Link>
        </div>
        <p className="muted small">O relatório abre pronto para imprimir. Na janela de impressão, escolha "Salvar como PDF".</p>
      </div>
      <div className="stack stack--tight">
        <h3>Backup completo</h3>
        <p className="muted small">
          Todos os seus dados (categorias, lançamentos, fixas, metas e investimentos) num arquivo JSON. Guarde em
          local seguro: ele contém sua vida financeira.
        </p>
        <div>
          <Button
            type="button"
            variant="secondary"
            loading={busy === "backup"}
            onClick={() => get("backup", "/export/backup", "meu-orcamento-backup.json")}
          >
            Baixar backup (JSON)
          </Button>
        </div>
      </div>
    </section>
  );
}

export default function DataPage() {
  return (
    <div className="stack">
      <PageHeader title="Importar e exportar" subtitle="Traga extratos e o arquivo do app antigo; leve seus dados em CSV, Excel, PDF ou backup." />
      <StatementImport />
      <div className="layout-2">
        <LegacyImport />
        <Export />
      </div>
    </div>
  );
}
