import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router";

import { analysisApi, type ProjectionPoint, type Rule, type Score } from "../api/analysis";
import { useMonth } from "../api/budget";
import { errorMessage } from "../api/client";
import { Bar } from "../components/budget";
import { LineChart } from "../components/charts";
import { Alert, Button } from "../components/ui";
import { addMonths, money, monthLabel, percent, thisMonth } from "../lib/format";

type Tab = "geral" | "comparar" | "projecao" | "simulador";
const TABS: [Tab, string][] = [
  ["geral", "Visão geral"],
  ["comparar", "Comparar meses"],
  ["projecao", "Projeção"],
  ["simulador", "Simulador"],
];

const SCORE_COLORS: Record<string, string> = {
  Excelente: "var(--ok)",
  Boa: "var(--ok)",
  Regular: "#d98c3f",
  Atenção: "#d98c3f",
  Crítica: "var(--error)",
};

function MonthPicker({ value, onChange, label }: { value: string; onChange: (v: string) => void; label: string }) {
  return (
    <label className="month-picker">
      {label}
      <input type="month" value={value} onChange={(e) => e.target.value && onChange(e.target.value)} />
    </label>
  );
}

// ---------------------------------------------------------------- visão geral

function ScoreCard({ score }: { score: Score }) {
  const color = SCORE_COLORS[score.label] ?? "var(--muted)";
  return (
    <section className="card stack">
      <h2>Score financeiro</h2>
      <div className="score">
        <span className="score__num" style={{ color }}>
          {score.score ?? "—"}
        </span>
        <span className="muted">/ 100 · {score.label}</span>
      </div>
      {score.score !== null && <Bar pct={score.score} color={color} />}
      {score.components.length > 0 && (
        <ul className="breakdown">
          {score.components.map((c) => (
            <li key={c.key}>
              <div className="split">
                <span>{c.label}</span>
                <span className="muted small">
                  {c.points.toLocaleString("pt-BR")} de {c.max}
                </span>
              </div>
              <Bar pct={(c.points / c.max) * 100} color={color} />
              <span className="muted small">{c.detail}</span>
            </li>
          ))}
        </ul>
      )}
      <ul className="tips">
        {score.tips.map((tip) => (
          <li key={tip}>{tip}</li>
        ))}
      </ul>
    </section>
  );
}

function RuleLine({ label, value, pct, target, ok }: { label: string; value: string; pct: number | null; target: string; ok: boolean }) {
  return (
    <li className="split">
      <span>
        {label}: <strong>{money(value)}</strong> <span className="muted">({percent(pct)})</span>
      </span>
      <span className={ok ? "tone--ok" : "tone--error"}>
        {target} {ok ? "✓" : "⚠"}
      </span>
    </li>
  );
}

function RuleCard({ rule }: { rule: Rule }) {
  if (Number(rule.income) <= 0) {
    return (
      <section className="card stack">
        <h2>Regra 50/30/20</h2>
        <p className="muted">Lance a renda do mês para comparar com a regra.</p>
      </section>
    );
  }
  const scale = Math.max(100, (rule.needs_pct ?? 0) + (rule.wants_pct ?? 0));
  return (
    <section className="card stack">
      <h2>Regra 50/30/20</h2>
      <p className="muted small">
        Uma divisão clássica da renda: até 50% para necessidades, até 30% para desejos e pelo menos 20% para
        poupar ou investir. Necessidades são as contas em categorias essenciais.
      </p>
      <div className="stacked-bar" aria-hidden>
        <div className="stacked-bar__seg seg--needs" style={{ width: `${((rule.needs_pct ?? 0) / scale) * 100}%` }} />
        <div className="stacked-bar__seg seg--wants" style={{ width: `${((rule.wants_pct ?? 0) / scale) * 100}%` }} />
        <div className="stacked-bar__seg seg--savings" style={{ width: `${((rule.savings_pct ?? 0) / scale) * 100}%` }} />
      </div>
      <ul className="rule-lines">
        <RuleLine label="Necessidades" value={rule.needs} pct={rule.needs_pct} target="até 50%" ok={rule.needs_ok} />
        <RuleLine label="Desejos" value={rule.wants} pct={rule.wants_pct} target="até 30%" ok={rule.wants_ok} />
        <RuleLine label="Poupança" value={rule.savings} pct={rule.savings_pct} target="20% ou mais" ok={rule.savings_ok} />
      </ul>
      {Number(rule.deficit) > 0 && (
        <Alert tone="error">As contas passam a renda em {money(rule.deficit)}.</Alert>
      )}
    </section>
  );
}

function OverviewTab({ month, setMonth }: { month: string; setMonth: (m: string) => void }) {
  const overview = useQuery({
    queryKey: ["budget", "analysis", "overview", month],
    queryFn: () => analysisApi.overview(month),
  });
  return (
    <div className="stack">
      <MonthPicker label="Mês analisado" value={month} onChange={setMonth} />
      {overview.isPending && <p className="muted">Carregando…</p>}
      {overview.isError && <Alert tone="error">{errorMessage(overview.error)}</Alert>}
      {overview.data && (
        <>
          <ScoreCard score={overview.data.score} />
          <RuleCard rule={overview.data.rule} />
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- comparar

function Delta({ value, invert = false }: { value: string; invert?: boolean }) {
  const n = Number(value);
  // Para contas, subir é ruim (invert); para renda e saldo, subir é bom.
  const good = invert ? n < 0 : n > 0;
  const tone = n === 0 ? "" : good ? "tone--ok" : "tone--error";
  return <span className={tone}>{n > 0 ? "+" : ""}{money(n)}</span>;
}

function CompareTab({ month }: { month: string }) {
  const [a, setA] = useState(addMonths(month, -1));
  const [b, setB] = useState(month);
  const comparison = useQuery({
    queryKey: ["budget", "analysis", "compare", a, b],
    queryFn: () => analysisApi.compare(a, b),
  });
  const data = comparison.data;

  return (
    <div className="stack">
      <div className="row">
        <MonthPicker label="Mês A" value={a} onChange={setA} />
        <MonthPicker label="Mês B" value={b} onChange={setB} />
      </div>
      {comparison.isError && <Alert tone="error">{errorMessage(comparison.error)}</Alert>}
      {data && (
        <section className="card">
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th />
                  <th className="num">{monthLabel(data.month_a, true)}</th>
                  <th className="num">{monthLabel(data.month_b, true)}</th>
                  <th className="num">Diferença</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td><strong>Renda</strong></td>
                  <td className="num">{money(data.income.a)}</td>
                  <td className="num">{money(data.income.b)}</td>
                  <td className="num"><Delta value={data.income.delta} /></td>
                </tr>
                <tr>
                  <td><strong>Contas</strong></td>
                  <td className="num">{money(data.expenses.a)}</td>
                  <td className="num">{money(data.expenses.b)}</td>
                  <td className="num"><Delta value={data.expenses.delta} invert /></td>
                </tr>
                <tr>
                  <td><strong>Saldo</strong></td>
                  <td className="num">{money(data.balance.a)}</td>
                  <td className="num">{money(data.balance.b)}</td>
                  <td className="num"><Delta value={data.balance.delta} /></td>
                </tr>
                {data.categories.length > 0 && (
                  <tr>
                    <td colSpan={4} className="muted small table__group">Por categoria</td>
                  </tr>
                )}
                {data.categories.map((c) => (
                  <tr key={c.category_id ?? "none"}>
                    <td>{c.name}</td>
                    <td className="num">{money(c.a)}</td>
                    <td className="num">{money(c.b)}</td>
                    <td className="num">
                      <Delta value={c.delta} invert />
                      {c.delta_pct !== null && c.delta_pct !== 0 && (
                        <span className="muted small"> ({c.delta_pct > 0 ? "+" : ""}{percent(c.delta_pct)})</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- projeção

function useProjection() {
  const start = thisMonth();
  return useQuery({
    queryKey: ["budget", "analysis", "projection", start],
    queryFn: () => analysisApi.projection(start, 12),
  });
}

function ProjectionTab() {
  const projection = useProjection();
  const points = projection.data ?? [];
  const totals = useMemo(
    () => ({
      income: points.reduce((s, p) => s + Number(p.income), 0),
      expenses: points.reduce((s, p) => s + Number(p.expenses), 0),
      final: points.length ? Number(points[points.length - 1].cumulative) : 0,
    }),
    [points],
  );

  return (
    <div className="stack">
      <p className="muted">
        Próximos 12 meses com base nas suas contas e rendas fixas, nas parcelas que faltam e no que já foi
        lançado. Contas avulsas futuras ainda não entram.
      </p>
      {projection.isPending && <p className="muted">Carregando…</p>}
      {projection.isError && <Alert tone="error">{errorMessage(projection.error)}</Alert>}
      {points.length > 0 && (
        <>
          <section className="card stack">
            <div className="stats">
              <div className="stat">
                <span className="stat__label">Renda prevista</span>
                <strong className="stat__value">{money(totals.income)}</strong>
              </div>
              <div className="stat">
                <span className="stat__label">Contas previstas</span>
                <strong className="stat__value">{money(totals.expenses)}</strong>
              </div>
              <div className="stat">
                <span className="stat__label">Saldo acumulado</span>
                <strong className={`stat__value ${totals.final < 0 ? "tone--error" : "tone--ok"}`}>
                  {money(totals.final)}
                </strong>
              </div>
            </div>
            <LineChart
              labels={points.map((p) => monthLabel(p.month, true))}
              series={[{ label: "Saldo acumulado", color: "var(--accent)", values: points.map((p) => Number(p.cumulative)) }]}
            />
          </section>
          <section className="card">
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Mês</th>
                    <th className="num">Renda</th>
                    <th className="num">Contas</th>
                    <th className="num">Saldo</th>
                    <th className="num">Acumulado</th>
                  </tr>
                </thead>
                <tbody>
                  {points.map((p) => (
                    <tr key={p.month}>
                      <td>
                        <Link to={`/orcamento/${p.month}`}>{monthLabel(p.month)}</Link>
                      </td>
                      <td className="num">{money(p.income)}</td>
                      <td className="num">{money(p.expenses)}</td>
                      <td className={`num ${Number(p.balance) < 0 ? "tone--error" : ""}`}>{money(p.balance)}</td>
                      <td className={`num ${Number(p.cumulative) < 0 ? "tone--error" : ""}`}>{money(p.cumulative)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- simulador

type Sim = { incomePct: number; expensePct: number; cutWantsPct: number; extra: number };
const ZERO_SIM: Sim = { incomePct: 0, expensePct: 0, cutWantsPct: 0, extra: 0 };

function Slider({ label, value, min, max, onChange }: { label: string; value: number; min: number; max: number; onChange: (v: number) => void }) {
  return (
    <label className="slider">
      <span className="split">
        <span>{label}</span>
        <strong>{value > 0 ? "+" : ""}{value}%</strong>
      </span>
      <input type="range" min={min} max={max} step={1} value={value} onChange={(e) => onChange(Number(e.target.value))} />
    </label>
  );
}

function simulate(point: { income: number; expenses: number }, wants: number, sim: Sim) {
  const income = point.income * (1 + sim.incomePct / 100);
  const cut = wants * (sim.cutWantsPct / 100);
  const expenses = Math.max(0, (point.expenses - cut) * (1 + sim.expensePct / 100) + sim.extra);
  return { income, expenses, balance: income - expenses };
}

function SimulatorTab() {
  const month = thisMonth();
  const current = useMonth(month);
  const projection = useProjection();
  const [sim, setSim] = useState<Sim>(ZERO_SIM);
  const set = (patch: Partial<Sim>) => setSim((s) => ({ ...s, ...patch }));

  if (current.isPending || projection.isPending) return <p className="muted">Carregando…</p>;
  if (current.isError) return <Alert tone="error">{errorMessage(current.error)}</Alert>;
  if (projection.isError) return <Alert tone="error">{errorMessage(projection.error)}</Alert>;

  const s = current.data.summary;
  const wants = Number(s.non_essential_total);
  const real = { income: Number(s.income_total), expenses: Number(s.expense_total) };
  const simulated = simulate(real, wants, sim);
  const realBalance = real.income - real.expenses;
  const delta = simulated.balance - realBalance;
  const committed = simulated.income > 0 ? (simulated.expenses / simulated.income) * 100 : null;

  // Aplica o mesmo cenário em cada mês da projeção, com os gastos não essenciais de cada mês.
  const cumulative = (points: ProjectionPoint[], scenario: Sim) => {
    let total = 0;
    return points.map((p) => {
      const point = { income: Number(p.income), expenses: Number(p.expenses) };
      total += simulate(point, Number(p.non_essential), scenario).balance;
      return total;
    });
  };
  const labels = projection.data.map((p) => monthLabel(p.month, true));
  const base = cumulative(projection.data, ZERO_SIM);
  const scenario = cumulative(projection.data, sim);

  return (
    <div className="stack">
      <p className="muted">
        E se a renda ou as contas mudassem? Ajuste os controles e compare com {monthLabel(month).toLowerCase()} e
        com a projeção dos próximos 12 meses. Nada aqui altera seus dados.
      </p>
      <section className="card stack">
        <Slider label="Renda" value={sim.incomePct} min={-50} max={50} onChange={(v) => set({ incomePct: v })} />
        <Slider label="Todas as contas" value={sim.expensePct} min={-50} max={50} onChange={(v) => set({ expensePct: v })} />
        <Slider label="Corte nos gastos não essenciais" value={-sim.cutWantsPct} min={-100} max={0} onChange={(v) => set({ cutWantsPct: -v })} />
        <label className="slider">
          <span>Nova conta mensal (ex.: financiamento, plano de saúde)</span>
          <input
            type="number"
            min={0}
            step={50}
            inputMode="decimal"
            value={sim.extra || ""}
            placeholder="R$ 0"
            onChange={(e) => set({ extra: Math.max(0, Number(e.target.value) || 0) })}
          />
        </label>
        <div>
          <Button type="button" variant="secondary" onClick={() => setSim(ZERO_SIM)}>
            Zerar simulação
          </Button>
        </div>
      </section>

      <section className="card stack">
        <h2>Resultado no mês</h2>
        <div className="stats">
          <div className="stat">
            <span className="stat__label">Renda</span>
            <strong className="stat__value">{money(simulated.income)}</strong>
          </div>
          <div className="stat">
            <span className="stat__label">Contas</span>
            <strong className="stat__value">{money(simulated.expenses)}</strong>
          </div>
          <div className="stat">
            <span className="stat__label">Saldo</span>
            <strong className={`stat__value ${simulated.balance < 0 ? "tone--error" : "tone--ok"}`}>
              {money(simulated.balance)}
            </strong>
          </div>
          <div className="stat">
            <span className="stat__label">Comprometido</span>
            <strong className="stat__value">{percent(committed === null ? null : Math.round(committed * 10) / 10)}</strong>
          </div>
        </div>
        <p className="small">
          Diferença para o real:{" "}
          <strong className={delta >= 0 ? "tone--ok" : "tone--error"}>
            {delta > 0 ? "+" : ""}
            {money(delta)} por mês
          </strong>
          {" · em 12 meses: "}
          <strong className={scenario[scenario.length - 1] - base[base.length - 1] >= 0 ? "tone--ok" : "tone--error"}>
            {money(scenario[scenario.length - 1] - base[base.length - 1])}
          </strong>
        </p>
        <LineChart
          labels={labels}
          series={[
            { label: "Projeção atual", color: "var(--muted)", values: base, dashed: true },
            { label: "Com a simulação", color: "var(--accent)", values: scenario },
          ]}
        />
      </section>
    </div>
  );
}

// ---------------------------------------------------------------- página

export default function Analysis() {
  const [params, setParams] = useSearchParams();
  const tab = (TABS.find(([key]) => key === params.get("aba"))?.[0] ?? "geral") as Tab;
  const [month, setMonth] = useState(thisMonth());

  return (
    <div className="stack">
      <h1>Análises</h1>
      <div className="tabs" role="tablist">
        {TABS.map(([key, label]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={tab === key}
            className={`tab ${tab === key ? "tab--active" : ""}`}
            onClick={() => setParams({ aba: key }, { replace: true })}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "geral" && <OverviewTab month={month} setMonth={setMonth} />}
      {tab === "comparar" && <CompareTab month={month} />}
      {tab === "projecao" && <ProjectionTab />}
      {tab === "simulador" && <SimulatorTab />}
    </div>
  );
}
