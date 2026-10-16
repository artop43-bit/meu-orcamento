import { money } from "../lib/format";

// Gráficos da Análise financeira. Todos têm descrição para leitor de tela e a opção
// "Ver dados em tabela" com os números exatos.

/** Cores para categorias sem cor definida (e para "Outras"). */
export const FALLBACK_COLORS = ["#4e79a7", "#f28e2b", "#59a14f", "#e15759", "#76b7b2", "#b07aa1", "#bab0ac"];

/** "+1,2 mil", "-850": cabe embaixo de barras estreitas. */
export function compactMoney(value: number): string {
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "+";
  if (abs >= 1000) return `${sign}${(abs / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} mil`;
  return `${sign}${Math.round(abs)}`;
}

/** Tabela recolhida com os números do gráfico. */
export function ChartData({ headers, rows }: { headers: string[]; rows: (string | number)[][] }) {
  return (
    <details className="chart-data">
      <summary>Ver dados em tabela</summary>
      <div className="table-wrap">
        <table className="table table--compact">
          <thead>
            <tr>
              {headers.map((h, i) => (
                <th key={h} className={i > 0 ? "num" : undefined}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, r) => (
              <tr key={r}>
                {row.map((cell, i) => (
                  <td key={i} className={i > 0 ? "num" : undefined}>
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

export type IncomeExpensePoint = { label: string; title: string; income: number; expenses: number; balance: number };

/** Renda × gastos por mês (barras lado a lado) com a sobra ou falta escrita embaixo. */
export function IncomeExpenseChart({ points }: { points: IncomeExpensePoint[] }) {
  const max = Math.max(1, ...points.flatMap((p) => [p.income, p.expenses]));
  const first = points[0]?.title;
  const last = points[points.length - 1]?.title;
  return (
    <figure className="bars-chart bars-chart--recent" data-no-swipe>
      <div className="bars-chart__plot" role="img" aria-label={`Renda e gastos de ${first} a ${last}.`}>
        {points.map((p) => (
          <div key={p.title} className="bars-chart__col" title={`${p.title}: renda ${money(p.income)}, gastos ${money(p.expenses)}`}>
            <div className="bars-chart__bars">
              <span className="bars-chart__bar chart__bar--income" style={{ height: `${(p.income / max) * 100}%` }} />
              <span className="bars-chart__bar chart__bar--expense" style={{ height: `${(p.expenses / max) * 100}%` }} />
            </div>
            <span className={`bars-chart__balance ${p.balance < 0 ? "tone--error" : "tone--ok"}`}>
              {p.income || p.expenses ? compactMoney(p.balance) : "–"}
            </span>
            <span className="bars-chart__label">{p.label}</span>
          </div>
        ))}
      </div>
      <figcaption className="legend">
        <span>
          <i className="swatch chart__bar--income" /> Renda
        </span>
        <span>
          <i className="swatch chart__bar--expense" /> Gastos
        </span>
        <span className="muted">Embaixo: sobra (verde) ou falta (vermelho)</span>
      </figcaption>
    </figure>
  );
}

export type StackSeries = { name: string; color: string; values: number[] };

/** Gastos por categoria ao longo dos meses (barras empilhadas). */
export function StackedBars({ labels, titles, series }: { labels: string[]; titles: string[]; series: StackSeries[] }) {
  const totals = labels.map((_, i) => series.reduce((sum, s) => sum + s.values[i], 0));
  const max = Math.max(1, ...totals);
  return (
    <figure className="bars-chart" data-no-swipe>
      <div className="bars-chart__plot" role="img" aria-label="Gastos por categoria em cada mês.">
        {labels.map((label, i) => (
          <div key={titles[i]} className="bars-chart__col" title={`${titles[i]}: ${money(totals[i])}`}>
            <div className="bars-chart__bars">
              <span className="bars-chart__stack" style={{ height: `${(totals[i] / max) * 100}%` }}>
                {series.map((s) =>
                  s.values[i] > 0 ? (
                    <span key={s.name} style={{ flexGrow: s.values[i], background: s.color }} title={`${s.name}: ${money(s.values[i])}`} />
                  ) : null,
                )}
              </span>
            </div>
            <span className="bars-chart__label">{label}</span>
          </div>
        ))}
      </div>
      <figcaption className="legend">
        {series.map((s) => (
          <span key={s.name}>
            <i className="swatch" style={{ background: s.color }} /> {s.name}
          </span>
        ))}
      </figcaption>
    </figure>
  );
}

export type Slice = { name: string; value: number; color: string };

/** Rosca com o total no meio: para onde foi o dinheiro do mês. */
export function Donut({ slices, center, caption }: { slices: Slice[]; center: string; caption: string }) {
  const total = slices.reduce((sum, s) => sum + s.value, 0) || 1;
  const r = 15.9155; // circunferência = 100, então cada fatia usa a própria porcentagem
  let start = 0;
  return (
    <figure className="donut">
      <svg
        viewBox="0 0 42 42"
        role="img"
        aria-label={`${caption}: ${slices.map((s) => `${s.name} ${Math.round((s.value / total) * 100)}%`).join(", ")}`}
      >
        <circle cx="21" cy="21" r={r} fill="none" stroke="var(--border)" strokeWidth="5" />
        {slices.map((s) => {
          const pct = (s.value / total) * 100;
          const circle = (
            <circle
              key={s.name}
              cx="21"
              cy="21"
              r={r}
              fill="none"
              stroke={s.color}
              strokeWidth="5"
              strokeDasharray={`${pct} ${100 - pct}`}
              strokeDashoffset={25 - start}
            />
          );
          start += pct;
          return circle;
        })}
        <text x="21" y="20.5" textAnchor="middle" className="donut__label">
          Total
        </text>
        <text x="21" y="25" textAnchor="middle" className="donut__center">
          {center}
        </text>
      </svg>
      <figcaption>
        <ul className="donut__legend">
          {slices.map((s) => (
            <li key={s.name}>
              <i className="swatch" style={{ background: s.color }} />
              <span className="grow">{s.name}</span>
              <span className="num">{money(s.value)}</span>
              <span className="muted small donut__pct">{Math.round((s.value / total) * 100)}%</span>
            </li>
          ))}
        </ul>
      </figcaption>
    </figure>
  );
}
