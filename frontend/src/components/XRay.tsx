import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api, errorMessage } from "../api/client";
import { money, percent } from "../lib/format";
import { Tip } from "./help";
import { Alert, LoadingRegion, Skeleton } from "./ui";

type Fees = { year: number; total: string; groups: { key: string; label: string; total: string; examples: { description: string; amount: string }[] }[] };
type Inflation = {
  categories: { category_id: string | null; name: string; before: string; now: string; change_pct: number }[];
  total_change_pct: number | null;
  ipca_12m: number | null;
};

/** Insights › Categorias (v1.4): tarifas, anuidades, IOF, juros e multas pagos no ano. */
export function FeesCard() {
  const thisYear = new Date().getFullYear();
  const [year, setYear] = useState(thisYear);
  const data = useQuery({ queryKey: ["budget", "fees", year], queryFn: () => api.get<Fees>(`/analysis/fees?year=${year}`) });
  return (
    <section className="card stack">
      <div className="section-header">
        <h2>
          Tarifas e juros{" "}
          <Tip>Encontrados pela descrição das despesas (tarifa, anuidade, IOF, juros, multa…) e pelos juros das parcelas dos financiamentos.</Tip>
        </h2>
        <select value={year} onChange={(e) => setYear(Number(e.target.value))} aria-label="Ano">
          {[thisYear, thisYear - 1, thisYear - 2].map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
        </select>
      </div>
      {data.isPending && (
        <LoadingRegion label="Carregando as tarifas">
          <Skeleton height={80} />
        </LoadingRegion>
      )}
      {data.isError && <Alert tone="error">{errorMessage(data.error)}</Alert>}
      {data.data &&
        (data.data.groups.length === 0 ? (
          <p className="muted" style={{ margin: 0 }}>
            Nenhuma tarifa ou juro encontrado em {year}.
          </p>
        ) : (
          <>
            <p style={{ margin: 0 }}>
              Em {year}, <strong>{money(data.data.total)}</strong> foram para tarifas, juros e encargos.
            </p>
            <ul className="items">
              {data.data.groups.map((g) => (
                <li key={g.key} className="item">
                  <span className="item__main">
                    <span className="item__title">{g.label}</span>
                    {g.examples.length > 0 && <span className="item__meta">{g.examples.map((e) => e.description).join(" · ")}</span>}
                  </span>
                  <strong className="num">{money(g.total)}</strong>
                </li>
              ))}
            </ul>
          </>
        ))}
    </section>
  );
}

/** Insights › Categorias (v1.4): os seus gastos subiram mais ou menos que o IPCA? */
export function PersonalInflationCard() {
  const data = useQuery({ queryKey: ["budget", "personal-inflation"], queryFn: () => api.get<Inflation>("/analysis/personal-inflation") });
  if (data.isPending || data.isError || data.data.categories.length === 0) return null;
  const d = data.data;
  const ipca = d.ipca_12m;
  return (
    <section className="card stack">
      <h2>
        Sua inflação × IPCA{" "}
        <Tip>Gastos dos últimos 12 meses comparados com os 12 meses anteriores, por categoria. Parcelas e financiamentos ficam de fora.</Tip>
      </h2>
      {d.total_change_pct !== null && (
        <p style={{ margin: 0 }}>
          Seus gastos variaram <strong className={d.total_change_pct > (ipca ?? 0) ? "tone--error" : undefined}>{percent(d.total_change_pct)}</strong>
          {ipca !== null && (
            <>
              {" "}
              em 12 meses; o IPCA foi <strong>{percent(ipca)}</strong>.
            </>
          )}
        </p>
      )}
      <ul className="items">
        {d.categories.map((c) => (
          <li key={c.category_id ?? "none"} className="item">
            <span className="item__main">
              <span className="item__title">{c.name}</span>
              <span className="item__meta">
                {money(c.before)} → {money(c.now)}
              </span>
            </span>
            <strong className={`num ${ipca !== null && c.change_pct > ipca ? "tone--error" : ""}`}>
              {c.change_pct > 0 ? "+" : ""}
              {percent(c.change_pct)}
            </strong>
          </li>
        ))}
      </ul>
    </section>
  );
}
