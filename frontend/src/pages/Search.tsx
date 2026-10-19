import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search as SearchIcon } from "lucide-react";
import { Link, useSearchParams } from "react-router";

import { PAYMENT_METHODS, paymentLabel, useCategories } from "../api/budget";
import { errorMessage } from "../api/client";
import { moneyApi } from "../api/money";
import { CategorySelect } from "../components/budget";
import { DateField } from "../components/DateField";
import { Alert, Button, LoadingRegion, PageHeader, Skeleton } from "../components/ui";
import { money, monthLabel, parseMoney, shortDate } from "../lib/format";

const FIELDS = ["q", "start", "end", "min_amount", "max_amount", "payment_method", "category_id", "kind"] as const;

/** Busca em todos os meses (despesas e receitas). */
export default function SearchPage() {
  const [params, setParams] = useSearchParams();
  const categories = useCategories();
  const initial = Object.fromEntries(FIELDS.map((f) => [f, params.get(f) ?? ""])) as Record<(typeof FIELDS)[number], string>;
  const [form, setForm] = useState(initial);
  const active = FIELDS.some((f) => params.get(f));
  const query = Object.fromEntries(FIELDS.map((f) => [f, params.get(f) ?? ""]));
  const results = useQuery({
    queryKey: ["budget", "search", query],
    queryFn: () => moneyApi.search(query),
    enabled: active,
  });
  const names = new Map((categories.data ?? []).map((c) => [c.id, c.name]));

  function set<K extends keyof typeof form>(key: K, value: string) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    const next: Record<string, string> = {};
    for (const f of FIELDS) {
      let v = form[f].trim();
      if ((f === "min_amount" || f === "max_amount") && v) v = parseMoney(v) ?? "";
      if (v) next[f] = v;
    }
    setParams(next);
  }

  const data = results.data;
  return (
    <>
      <PageHeader title="Busca" subtitle="Encontre despesas e receitas de qualquer mês." />
      <form className="card stack" onSubmit={submit} role="search">
        <label className="list-tools__search">
          <SearchIcon size={16} aria-hidden />
          <span className="sr-only">Descrição ou observação</span>
          <input type="search" value={form.q} onChange={(e) => set("q", e.target.value)} placeholder="Descrição ou observação" autoFocus />
        </label>
        <div className="grid-3">
          <label>
            De
            <DateField value={form.start} onChange={(v) => set("start", v)} />
          </label>
          <label>
            Até
            <DateField value={form.end} onChange={(v) => set("end", v)} />
          </label>
          <label>
            Tipo
            <select value={form.kind} onChange={(e) => set("kind", e.target.value)}>
              <option value="">Despesas e receitas</option>
              <option value="expense">Só despesas</option>
              <option value="income">Só receitas</option>
            </select>
          </label>
          <label>
            Valor mínimo
            <input inputMode="decimal" value={form.min_amount} onChange={(e) => set("min_amount", e.target.value)} placeholder="0,00" />
          </label>
          <label>
            Valor máximo
            <input inputMode="decimal" value={form.max_amount} onChange={(e) => set("max_amount", e.target.value)} placeholder="0,00" />
          </label>
          <label>
            Forma de pagamento
            <select value={form.payment_method} onChange={(e) => set("payment_method", e.target.value)}>
              <option value="">Todas</option>
              {PAYMENT_METHODS.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Categoria
            <CategorySelect categories={categories.data ?? []} value={form.category_id} onChange={(v) => set("category_id", v)} />
          </label>
        </div>
        <div className="form-actions">
          <Button
            type="button"
            variant="secondary"
            onClick={() => {
              setForm(Object.fromEntries(FIELDS.map((f) => [f, ""])) as typeof form);
              setParams({});
            }}
          >
            Limpar
          </Button>
          <Button type="submit">Buscar</Button>
        </div>
      </form>
      {results.isFetching && (
        <LoadingRegion label="Buscando">
          <Skeleton height={160} />
        </LoadingRegion>
      )}
      {results.isError && <Alert tone="error">{errorMessage(results.error)}</Alert>}
      {data && (
        <section className="card stack" style={{ marginTop: 20 }}>
          <p className="muted" style={{ margin: 0 }} role="status">
            {data.count} resultado(s) · despesas {money(data.total_expenses)} · receitas {money(data.total_incomes)}
            {data.count > data.results.length && ` · exibindo os ${data.results.length} mais recentes`}
          </p>
          {data.results.length > 0 && (
            <div className="table-wrap" tabIndex={0} role="region" aria-label="Resultados">
              <table className="table">
                <thead>
                  <tr>
                    <th scope="col">Data</th>
                    <th scope="col">Descrição</th>
                    <th scope="col">Categoria</th>
                    <th scope="col">Pagamento</th>
                    <th scope="col" className="num">
                      Valor
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.results.map((r) => (
                    <tr key={`${r.kind}-${r.id}`}>
                      <td>
                        <Link to={`/orcamento/${r.month}`}>{r.date ? `${shortDate(r.date)}/${r.date.slice(2, 4)}` : monthLabel(r.month, true)}</Link>
                      </td>
                      <td className="wrap">{r.description}</td>
                      <td>{r.kind === "income" ? "Receita" : r.category_id ? names.get(r.category_id) : "Sem categoria"}</td>
                      <td>{paymentLabel(r.payment_method) ?? "—"}</td>
                      <td className={`num ${r.kind === "income" ? "tone--ok" : ""}`}>
                        {r.kind === "income" ? "+" : "−"}
                        {money(r.amount)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
    </>
  );
}
