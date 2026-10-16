import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CalendarRange, History as HistoryIcon, PiggyBank, Receipt } from "lucide-react";
import { Link, useSearchParams } from "react-router";

import { analysisApi, type Overview, type Rule, type Score } from "../api/analysis";
import { useCategories, useMonth, type CategoryTotal } from "../api/budget";
import { insightsApi, type Insights, type Trends } from "../api/insights";
import { errorMessage } from "../api/client";
import { Bar, Stat } from "../components/budget";
import { AlertsCard, ConsultantCard, useInsights } from "../components/consultant";
import { ChartData, Donut, FALLBACK_COLORS, IncomeExpenseChart, StackedBars } from "../components/dashboardCharts";
import { LineChart } from "../components/charts";
import { Alert, Button, Kpi, LoadingRegion, PageHeader, Skeleton } from "../components/ui";
import { addMonths, money, monthLabel, percent, thisMonth } from "../lib/format";
import { cumulativeBalance, simulate, ZERO_SIM, type Sim } from "../lib/simulate";

type Tab = "geral" | "comparar" | "projecao" | "simulador";
const TABS: [Tab, string][] = [
  ["geral", "Painel"],
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

function pctChange(now: number, before: number | null): number | null {
  if (before === null || before <= 0) return null;
  return ((now - before) / before) * 100;
}

/** "12% acima" / "8% abaixo", com a cor de bom ou ruim (para gastos, subir é ruim). */
function ChangeFoot({ change, of }: { change: number | null; of: string }) {
  if (change === null) return <>Sem dados {of}</>;
  const up = change > 0;
  return (
    <span className={Math.abs(change) < 1 ? "" : up ? "tone--error" : "tone--ok"}>
      {Math.abs(change).toFixed(0)}% {up ? "acima" : "abaixo"} {of}
    </span>
  );
}

function DashboardTab({ month, setMonth }: { month: string; setMonth: (m: string) => void }) {
  const insights = useInsights(month);
  const trends = useQuery({
    queryKey: ["budget", "analysis", "trends", month],
    queryFn: () => insightsApi.trends(month, 12),
  });
  const overview = useQuery({
    queryKey: ["budget", "analysis", "overview", month],
    queryFn: () => analysisApi.overview(month),
  });
  const monthData = useMonth(month);
  const categories = useCategories();

  const loading = insights.isPending || trends.isPending || overview.isPending;
  const error = insights.error ?? trends.error ?? overview.error;

  return (
    <div className="stack" style={{ gap: 20 }}>
      <MonthPicker label="Mês analisado" value={month} onChange={setMonth} />
      {loading && (
        <LoadingRegion label="Carregando a análise">
          <div className="layout-main-side">
            <div className="card stack">
              <Skeleton height={28} width="60%" />
              <Skeleton height={60} />
              <Skeleton height={40} />
            </div>
            <div className="card stack">
              <Skeleton height={20} width="40%" />
              <Skeleton height={60} />
            </div>
          </div>
        </LoadingRegion>
      )}
      {error && <Alert tone="error">{errorMessage(error)}</Alert>}
      {insights.data && trends.data && overview.data && (
        <DashboardContent
          month={month}
          insights={insights.data}
          trends={trends.data}
          overview={overview.data}
          byCategory={monthData.data?.summary.by_category ?? []}
          colors={new Map((categories.data ?? []).map((c) => [c.id, c.color]))}
        />
      )}
    </div>
  );
}

function DashboardContent({
  month,
  insights,
  trends,
  overview,
  byCategory,
  colors,
}: {
  month: string;
  insights: Insights;
  trends: Trends;
  overview: Overview;
  byCategory: CategoryTotal[];
  colors: Map<string, string | null>;
}) {
  if (insights.mood === "empty") {
    return (
      <div className="layout-main-side">
        <ConsultantCard data={insights} />
        <section className="card stack">
          <h2>Como começar</h2>
          <ol className="steps">
            <li>
              Cadastre o que se repete todo mês (salário, aluguel, internet) em <Link to="/fixas">Contas fixas</Link>.
            </li>
            <li>
              Lance os gastos do mês no <Link to={`/orcamento/${month}`}>Orçamento</Link>.
            </li>
            <li>
              Opcional: defina limites por categoria em <Link to="/categorias">Categorias</Link> para receber alertas.
            </li>
          </ol>
        </section>
      </div>
    );
  }

  const points = trends.months;
  const current = points[points.length - 1];
  const previous = points.slice(0, -1).filter((p) => p.has_data);
  const lastMonth = points[points.length - 2];
  const recent = previous.slice(-3);
  const avg3 = recent.length ? recent.reduce((sum, p) => sum + Number(p.expenses), 0) / recent.length : null;
  const expenses = Number(current.expenses);
  const ly = trends.same_month_last_year;

  // Pula os meses vazios do começo (conta nova), mantendo pelo menos 6 no gráfico.
  const firstWithData = Math.max(0, points.findIndex((p) => p.has_data));
  const chartPoints = points.slice(Math.min(firstWithData, points.length - 6)).map((p) => ({
    label: monthLabel(p.month, true).split(" ")[0],
    title: monthLabel(p.month),
    income: Number(p.income),
    expenses: Number(p.expenses),
    balance: Number(p.balance),
  }));

  const last6 = points.slice(-6);
  const stack = trends.categories.map((c, i) => ({
    name: c.name,
    color: c.color ?? FALLBACK_COLORS[i % FALLBACK_COLORS.length],
    values: c.totals.slice(-6).map(Number),
  }));

  const slices = byCategory.map((c, i) => ({
    name: c.name,
    value: Number(c.total),
    color: (c.category_id && colors.get(c.category_id)) || FALLBACK_COLORS[i % FALLBACK_COLORS.length],
  }));

  const wealth = trends.wealth;
  const goals = trends.goals;

  return (
    <>
      <div className="layout-main-side">
        <ConsultantCard data={insights} />
        <AlertsCard alerts={insights.alerts} />
      </div>

      <div className="kpis">
        <Kpi
          icon={<PiggyBank size={18} />}
          label="Taxa de poupança"
          value={insights.savings_pct === null ? "—" : percent(insights.savings_pct)}
          valueClass={insights.savings_pct !== null && insights.savings_pct < 0 ? "tone--error" : undefined}
          foot="Recomendado: 20% ou mais"
        />
        <Kpi
          icon={<Receipt size={18} />}
          tone="expense"
          label="Gastos × sua média"
          value={money(expenses)}
          foot={<ChangeFoot change={pctChange(expenses, avg3)} of="da média de 3 meses" />}
        />
        <Kpi
          icon={<CalendarRange size={18} />}
          tone="neutral"
          label="Mês anterior"
          value={lastMonth?.has_data ? money(lastMonth.expenses) : "—"}
          foot={
            <ChangeFoot
              change={lastMonth?.has_data ? pctChange(expenses, Number(lastMonth.expenses)) : null}
              of="do mês anterior"
            />
          }
        />
        <Kpi
          icon={<HistoryIcon size={18} />}
          tone="neutral"
          label={`${monthLabel(ly.month)}`}
          value={ly.has_data ? money(ly.expenses) : "—"}
          foot={<ChangeFoot change={ly.has_data ? pctChange(expenses, Number(ly.expenses)) : null} of="do ano passado" />}
        />
      </div>

      <section className="card stack">
        <h2>Renda, gastos e sobra · 12 meses</h2>
        <IncomeExpenseChart points={chartPoints} />
        <ChartData
          headers={["Mês", "Renda", "Gastos", "Sobra", "Poupança"]}
          rows={points
            .filter((p) => p.has_data)
            .map((p) => [monthLabel(p.month), money(p.income), money(p.expenses), money(p.balance), percent(p.savings_pct)])}
        />
      </section>

      <div className="layout-2">
        <section className="card stack">
          <h2>Para onde foi o dinheiro</h2>
          {slices.length === 0 ? (
            <p className="muted">Nenhum gasto lançado neste mês.</p>
          ) : (
            <Donut slices={slices} center={compactTotal(expenses)} caption={`Gastos de ${monthLabel(month)}`} />
          )}
        </section>
        <section className="card stack">
          <h2>Gastos por categoria · 6 meses</h2>
          {stack.length === 0 ? (
            <p className="muted">Sem gastos no período.</p>
          ) : (
            <>
              <StackedBars
                labels={last6.map((p) => monthLabel(p.month, true).split(" ")[0])}
                titles={last6.map((p) => monthLabel(p.month))}
                series={stack}
              />
              <ChartData
                headers={["Categoria", ...last6.map((p) => monthLabel(p.month, true))]}
                rows={stack.map((s) => [s.name, ...s.values.map((v) => money(v))])}
              />
            </>
          )}
        </section>
      </div>

      <div className="layout-2">
        <ScoreCard score={overview.score} />
        <RuleCard rule={overview.rule} />
      </div>

      <section className="card stack">
        <h2>Patrimônio e metas</h2>
        <div className="stats">
          <Stat label="Investido" value={money(wealth.invested)} />
          <Stat label="Valor atual" value={money(wealth.current)} />
          <Stat label="Rendimento" value={money(wealth.return_value)} tone={Number(wealth.return_value) >= 0 ? "ok" : "error"} />
          <Stat label="Reserva de emergência" value={money(wealth.reserve)} />
        </div>
        {goals.count > 0 ? (
          <div className="stack stack--tight">
            <span className="small muted">
              {goals.count} meta(s): {money(goals.saved)} guardados de {money(goals.target)}
            </span>
            <Bar pct={(Number(goals.saved) / Math.max(Number(goals.target), 1)) * 100} />
          </div>
        ) : (
          <p className="muted small">
            Nenhuma meta ainda. <Link to="/metas">Crie uma meta</Link> para acompanhar quanto falta.
          </p>
        )}
        {Number(wealth.invested) === 0 && (
          <p className="muted small">
            Cadastre seus investimentos em <Link to="/investimentos">Investimentos</Link> para ver o patrimônio aqui.
          </p>
        )}
      </section>
    </>
  );
}

function compactTotal(value: number): string {
  if (value >= 10000) return `R$ ${(value / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} mil`;
  return money(value).replace(/,\d\d$/, "");
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
  const months = projection.data.map((p) => ({
    income: Number(p.income),
    expenses: Number(p.expenses),
    nonEssential: Number(p.non_essential),
  }));
  const labels = projection.data.map((p) => monthLabel(p.month, true));
  const base = cumulativeBalance(months, ZERO_SIM);
  const scenario = cumulativeBalance(months, sim);

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
  const fromLink = params.get("mes");
  const [month, setMonth] = useState(fromLink && /^\d{4}-\d{2}$/.test(fromLink) ? fromLink : thisMonth());

  return (
    <div className="stack">
      <PageHeader
        title="Análise financeira"
        subtitle="Seu consultor: como foi o mês, alertas, tendências, comparações e projeções."
      />
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
      {tab === "geral" && <DashboardTab month={month} setMonth={setMonth} />}
      {tab === "comparar" && <CompareTab month={month} />}
      {tab === "projecao" && <ProjectionTab />}
      {tab === "simulador" && <SimulatorTab />}
    </div>
  );
}
