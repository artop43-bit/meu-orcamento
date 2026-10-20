import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  ArrowDownLeft,
  CalendarRange,
  ChartBarDecreasing,
  ChartPie,
  FlaskConical,
  GitCompareArrows,
  HeartPulse,
  History as HistoryIcon,
  Landmark,
  LayoutDashboard,
  PiggyBank,
  Receipt,
  Scale,
  ShieldCheck,
  Sparkles,
  Tags,
  Target,
  Telescope,
  TrendingUp,
  WandSparkles,
  Calculator,
  type LucideIcon,
} from "lucide-react";
import { Link, useNavigate, useSearchParams } from "react-router";

import { analysisApi, type Rule, type Score } from "../api/analysis";
import { budgetApi, keys, useCategories, useMonth } from "../api/budget";
import { errorMessage } from "../api/client";
import { insightsApi, type AnalysisConfig, type SavedAnalysis } from "../api/insights";
import { AnalysisResult, Builder, PRESETS, SavedCard, useSaved } from "../components/AnalysisBuilder";
import { Bar } from "../components/budget";
import { Calculators } from "../components/Calculators";
import { Chart } from "../components/chart/Chart";
import { AlertsCard, ConsultantCard, useInsights } from "../components/consultant";
import { Alert, Button, Kpi, LoadingRegion, PageHeader, Skeleton } from "../components/ui";
import { useUndo } from "../components/undo";
import { prefersReducedMotion } from "../lib/announce";
import { addMonths, money, monthLabel, percent, thisMonth } from "../lib/format";
import { cumulativeBalance, simulate, ZERO_SIM, type Sim } from "../lib/simulate";
import { DateField } from "../components/DateField";

const SCORE_COLORS: Record<string, string> = {
  Excelente: "var(--ok)",
  Boa: "var(--ok)",
  Regular: "var(--warn)",
  Atenção: "var(--warn)",
  Crítica: "var(--error)",
};

function MonthPicker({ value, onChange, label }: { value: string; onChange: (v: string) => void; label: string }) {
  return (
    <label className="month-picker">
      {label}
      <DateField month value={value} onChange={(v) => v && onChange(v)} />
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
        <p className="muted">Registre as receitas do mês para comparar com a regra.</p>
      </section>
    );
  }
  const scale = Math.max(100, (rule.needs_pct ?? 0) + (rule.wants_pct ?? 0));
  return (
    <section className="card stack">
      <h2>Regra 50/30/20</h2>
      <p className="muted small">
        Referência de distribuição da receita: até 50% para necessidades, até 30% para desejos e ao menos 20% para
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
        <Alert tone="error">As despesas superam as receitas em {money(rule.deficit)}.</Alert>
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

function useTrends(month: string) {
  return useQuery({
    queryKey: ["budget", "analysis", "trends", month],
    queryFn: () => insightsApi.trends(month, 12),
    placeholderData: keepPreviousData,
  });
}

function SectionTitle({ title, text, month, setMonth }: { title: string; text?: string; month?: string; setMonth?: (m: string) => void }) {
  return (
    <div className="section-title">
      <div>
        <h2>{title}</h2>
        {text && <p>{text}</p>}
      </div>
      {month && setMonth && <MonthPicker label="Mês" value={month} onChange={setMonth} />}
    </div>
  );
}

function Loading() {
  return (
    <LoadingRegion label="Carregando">
      <div className="card stack">
        <Skeleton height={24} width="40%" />
        <Skeleton height={200} />
      </div>
    </LoadingRegion>
  );
}

const num = (v: string | null | undefined) => (v === null || v === undefined ? null : Number(v));

// ---------------------------------------------------------------- resumo

function SummarySection({ month, setMonth, goTo }: { month: string; setMonth: (m: string) => void; goTo: (s: SectionKey, config?: AnalysisConfig) => void }) {
  const insights = useInsights(month);
  const trends = useTrends(month);
  const saved = useSaved();
  const undo = useUndo();
  const pinned = (saved.data ?? []).filter((s) => s.pinned && !undo.isHidden(s.id));

  if (insights.isPending || trends.isPending) return <Loading />;
  if (insights.isError) return <Alert tone="error">{errorMessage(insights.error)}</Alert>;
  const data = insights.data;

  if (data.mood === "empty") {
    return (
      <>
        <SectionTitle title="Resumo" month={month} setMonth={setMonth} />
        <div className="layout-main-side">
          <ConsultantCard data={data} />
          <section className="card stack">
            <h2>Como começar</h2>
            <ol className="steps">
              <li>
                Configure lançamentos mensais (salário, aluguel, internet) em <Link to="/ajustes/recorrencias">Recorrências</Link>.
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
      </>
    );
  }

  const t = trends.data;
  const points = t?.months ?? [];
  const current = points[points.length - 1];
  const previous = points.slice(0, -1).filter((p) => p.has_data);
  const avg3 = previous.slice(-3).length ? previous.slice(-3).reduce((s, p) => s + Number(p.expenses), 0) / previous.slice(-3).length : null;
  const lastMonth = points[points.length - 2];
  const expenses = Number(current?.expenses ?? 0);

  return (
    <>
      <SectionTitle title="Resumo" text="Como está o mês, o que precisa de atenção e suas análises fixadas." month={month} setMonth={setMonth} />
      <div className="layout-main-side">
        <ConsultantCard data={data} />
        <AlertsCard alerts={data.alerts} />
      </div>
      {t && (
        <div className="kpis">
          <Kpi
            icon={<PiggyBank size={18} />}
            label="Taxa de poupança"
            value={data.savings_pct === null ? "—" : percent(data.savings_pct)}
            valueClass={data.savings_pct !== null && data.savings_pct < 0 ? "tone--error" : undefined}
            foot="Recomendado: 20% ou mais"
          />
          <Kpi icon={<Receipt size={18} />} tone="expense" label="Gastos do mês" value={money(expenses)} foot={<ChangeFoot change={pctChange(expenses, avg3)} of="da média de 3 meses" />} />
          <Kpi
            icon={<CalendarRange size={18} />}
            tone="neutral"
            label="Mês anterior"
            value={lastMonth?.has_data ? money(lastMonth.expenses) : "—"}
            foot={<ChangeFoot change={lastMonth?.has_data ? pctChange(expenses, Number(lastMonth.expenses)) : null} of="do mês anterior" />}
          />
          <Kpi
            icon={<HistoryIcon size={18} />}
            tone="neutral"
            label={monthLabel(t.same_month_last_year.month)}
            value={t.same_month_last_year.has_data ? money(t.same_month_last_year.expenses) : "—"}
            foot={<ChangeFoot change={t.same_month_last_year.has_data ? pctChange(expenses, Number(t.same_month_last_year.expenses)) : null} of="do ano passado" />}
          />
        </div>
      )}
      <div className="section-title">
        <div>
          <h2>Minhas análises</h2>
          <p>{pinned.length ? "Fixadas por você. Edite ou crie novas em Monte sua análise." : "Monte gráficos do seu jeito e fixe aqui."}</p>
        </div>
        <Button type="button" variant="secondary" onClick={() => goTo("monte")}>
          <WandSparkles size={16} /> Monte sua análise
        </Button>
      </div>
      {pinned.length > 0 ? (
        <div className="saved-grid">
          {pinned.map((item) => (
            <SavedCard key={item.id} item={item} compact />
          ))}
        </div>
      ) : (
        <div className="presets">
          {PRESETS.slice(0, 3).map((p) => (
            <button key={p.title} type="button" className="preset" onClick={() => goTo("monte", p.config)}>
              <span className="kpi__icon" aria-hidden>
                <Sparkles size={16} />
              </span>
              <span>
                <strong>{p.title}</strong>
                <small>{p.hint}</small>
              </span>
            </button>
          ))}
        </div>
      )}
    </>
  );
}

// ---------------------------------------------------------------- tendências

function TrendsSection({ month, setMonth }: { month: string; setMonth: (m: string) => void }) {
  const trends = useTrends(month);
  const navigate = useNavigate();
  if (trends.isPending) return <Loading />;
  if (trends.isError) return <Alert tone="error">{errorMessage(trends.error)}</Alert>;
  const t = trends.data;
  // Pula os meses vazios do começo (conta nova), mantendo pelo menos 6.
  const first = Math.max(0, t.months.findIndex((p) => p.has_data));
  const points = t.months.slice(Math.min(first, t.months.length - 6));
  const labels = points.map((p) => ({ key: p.month, label: p.month }));
  const open = (key: string) => navigate(`/orcamento/${key}`);

  return (
    <>
      <SectionTitle title="Tendências" text="Evolução de receitas, despesas e saldo até o mês selecionado." month={month} setMonth={setMonth} />
      <section className="card stack">
        <h3 className="builder__title">Receitas × despesas</h3>
        <Chart
          type="bar"
          labels={labels}
          series={[
            { key: "income", name: "Receitas", color: "var(--accent)", values: points.map((p) => Number(p.income)) },
            { key: "expenses", name: "Gastos", color: "var(--expense)", values: points.map((p) => Number(p.expenses)) },
          ]}
          monthLabels
          description="Receitas e despesas por mês"
          onSelect={open}
        />
      </section>
      <div className="layout-2">
        <section className="card stack">
          <h3 className="builder__title">Sobra ou falta no mês</h3>
          <Chart
            type="bar"
            labels={labels}
            series={[{ key: "balance", name: "Sobra", color: "var(--ok)", values: points.map((p) => (p.has_data ? Number(p.balance) : null)) }]}
            compare={t.averages.balance_6m ? { name: "Média de 6 meses", values: points.map(() => num(t.averages.balance_6m)) } : null}
            monthLabels
            height={220}
            description="Sobra por mês"
            onSelect={open}
          />
        </section>
        <section className="card stack">
          <h3 className="builder__title">Taxa de poupança</h3>
          <Chart
            type="area"
            labels={labels}
            series={[{ key: "savings", name: "Poupança", color: "var(--accent)", values: points.map((p) => p.savings_pct) }]}
            compare={{ name: "Meta de 20%", values: points.map(() => 20) }}
            unit="percent"
            monthLabels
            height={220}
            description="Taxa de poupança por mês"
            onSelect={open}
          />
        </section>
      </div>
      <div className="kpis">
        <Kpi icon={<ArrowDownLeft size={18} />} label="Receita média (6 meses)" value={money(t.averages.income_6m)} foot={`3 meses: ${money(t.averages.income_3m)}`} />
        <Kpi icon={<Receipt size={18} />} tone="expense" label="Gasto médio (6 meses)" value={money(t.averages.expenses_6m)} foot={`3 meses: ${money(t.averages.expenses_3m)}`} />
        <Kpi icon={<Scale size={18} />} tone="neutral" label="Sobra média (6 meses)" value={money(t.averages.balance_6m)} foot={`3 meses: ${money(t.averages.balance_3m)}`} />
        <Kpi
          icon={<HistoryIcon size={18} />}
          tone="neutral"
          label={`Ano passado (${monthLabel(t.same_month_last_year.month, true)})`}
          value={t.same_month_last_year.has_data ? money(t.same_month_last_year.balance) : "—"}
          foot={t.same_month_last_year.has_data ? "Sobra no mesmo mês" : "Sem dados"}
        />
      </div>
    </>
  );
}

// ---------------------------------------------------------------- categorias

function CategoriesSection({ month, setMonth }: { month: string; setMonth: (m: string) => void }) {
  const trends = useTrends(month);
  const monthData = useMonth(month);
  const [view, setView] = useState<"hbar" | "donut">("hbar");
  const colors = new Map((useCategories().data ?? []).map((c) => [c.id, c.color]));
  if (trends.isPending || monthData.isPending) return <Loading />;
  if (trends.isError) return <Alert tone="error">{errorMessage(trends.error)}</Alert>;
  const t = trends.data;
  const byCategory = monthData.data?.summary.by_category ?? [];
  const last6 = t.months.slice(-6);
  const withLimit = byCategory.filter((c) => c.limit);

  return (
    <>
      <SectionTitle title="Categorias" text="Para onde vai o dinheiro e como cada categoria evolui." month={month} setMonth={setMonth} />
      <div className="layout-2">
        <section className="card stack">
          <div className="builder__result-head">
            <h3 className="builder__title">{monthLabel(month)}</h3>
            <div className="chart-types" role="radiogroup" aria-label="Visualização">
              {(["hbar", "donut"] as const).map((type) => {
                const Icon = type === "hbar" ? ChartBarDecreasing : ChartPie;
                return (
                  <label key={type} title={type === "hbar" ? "Ranking" : "Rosca"}>
                    <input type="radio" name="cat-view" checked={view === type} onChange={() => setView(type)} aria-label={type === "hbar" ? "Ranking" : "Rosca"} />
                    <span>
                      <Icon size={18} aria-hidden />
                    </span>
                  </label>
                );
              })}
            </div>
          </div>
          {byCategory.length === 0 ? (
            <p className="muted">Nenhum gasto neste mês.</p>
          ) : (
            <Chart
              type={view}
              labels={byCategory.map((c) => ({ key: c.category_id ?? "none", label: c.name, color: c.category_id ? colors.get(c.category_id) : "#9aa3a0" }))}
              series={[{ key: "total", name: "Gastos", values: byCategory.map((c) => Number(c.total)) }]}
              description={`Gastos por categoria em ${monthLabel(month)}`}
            />
          )}
        </section>
        <section className="card stack">
          <h3 className="builder__title">Últimos 6 meses</h3>
          {t.categories.length === 0 ? (
            <p className="muted">Sem gastos no período.</p>
          ) : (
            <Chart
              type="stacked"
              labels={last6.map((p) => ({ key: p.month, label: p.month }))}
              series={t.categories.map((c) => ({ key: c.category_id ?? c.name, name: c.name, color: c.color, values: c.totals.slice(-6).map(Number) }))}
              monthLabels
              height={240}
              description="Gastos por categoria nos últimos 6 meses"
            />
          )}
        </section>
      </div>
      <section className="card stack">
        <h3 className="builder__title">Limites do mês</h3>
        {withLimit.length === 0 ? (
          <p className="muted" style={{ margin: 0 }}>
            Defina um limite mensal em <Link to="/categorias">Categorias</Link> para acompanhar aqui e receber alertas.
          </p>
        ) : (
          <ul className="breakdown">
            {withLimit.map((c) => (
              <li key={c.category_id ?? "none"}>
                <div className="split">
                  <span>{c.name}</span>
                  <span className="num">
                    {money(c.total)} <span className="muted small">de {money(c.limit)}</span>
                  </span>
                </div>
                <Bar pct={Math.min(c.limit_pct ?? 0, 100)} color={(c.limit_pct ?? 0) >= 100 ? "var(--error)" : (c.limit_pct ?? 0) >= 80 ? "var(--warn)" : undefined} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}

// ---------------------------------------------------------------- saúde financeira

function HealthSection({ month, setMonth }: { month: string; setMonth: (m: string) => void }) {
  const overview = useQuery({ queryKey: ["budget", "analysis", "overview", month], queryFn: () => analysisApi.overview(month) });
  if (overview.isPending) return <Loading />;
  if (overview.isError) return <Alert tone="error">{errorMessage(overview.error)}</Alert>;
  return (
    <>
      <SectionTitle title="Saúde financeira" text="Score de 0 a 100 e a regra 50/30/20 aplicada ao seu mês." month={month} setMonth={setMonth} />
      <div className="layout-2">
        <ScoreCard score={overview.data.score} />
        <RuleCard rule={overview.data.rule} />
      </div>
    </>
  );
}

// ---------------------------------------------------------------- patrimônio e metas

function WealthSection({ month }: { month: string }) {
  const trends = useTrends(month);
  const goals = useQuery({ queryKey: keys.goals, queryFn: budgetApi.goals });
  if (trends.isPending) return <Loading />;
  if (trends.isError) return <Alert tone="error">{errorMessage(trends.error)}</Alert>;
  const w = trends.data.wealth;
  const investConfig = PRESETS[PRESETS.length - 1].config;
  return (
    <>
      <SectionTitle title="Patrimônio e metas" text="Onde seu dinheiro está guardado e quanto falta para cada objetivo." />
      <div className="kpis">
        <Kpi icon={<Landmark size={18} />} label="Valor atual" value={money(w.current)} foot={`Investido: ${money(w.invested)}`} />
        <Kpi
          icon={<TrendingUp size={18} />}
          tone="neutral"
          label="Rendimento"
          value={money(w.return_value)}
          valueClass={Number(w.return_value) >= 0 ? "tone--ok" : "tone--error"}
          foot={Number(w.invested) > 0 ? percent((Number(w.return_value) / Number(w.invested)) * 100) : "—"}
        />
        <Kpi icon={<ShieldCheck size={18} />} tone="neutral" label="Reserva de emergência" value={money(w.reserve)} foot="Investimentos marcados como reserva" />
        <Kpi icon={<Target size={18} />} tone="neutral" label="Metas" value={money(trends.data.goals.saved)} foot={`de ${money(trends.data.goals.target)} (${trends.data.goals.count} meta(s))`} />
      </div>
      <div className="layout-2">
        {Number(w.current) > 0 ? (
          <AnalysisResult config={investConfig} title="Por tipo de investimento" height={220} />
        ) : (
          <section className="card stack">
            <h3 className="builder__title">Investimentos</h3>
            <p className="muted">
              Cadastre seus investimentos em <Link to="/investimentos">Investimentos</Link> para ver o patrimônio aqui.
            </p>
          </section>
        )}
        <section className="card stack">
          <h3 className="builder__title">Metas</h3>
          {(goals.data ?? []).length === 0 ? (
            <p className="muted">
              Nenhuma meta ainda. <Link to="/metas">Crie uma meta</Link>.
            </p>
          ) : (
            <ul className="breakdown">
              {(goals.data ?? []).map((g) => (
                <li key={g.id}>
                  <div className="split">
                    <span>{g.name}</span>
                    <span className="num">
                      {money(g.current_amount)} <span className="muted small">de {money(g.target_amount)}</span>
                    </span>
                  </div>
                  <Bar pct={g.progress_pct} />
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </>
  );
}

// ---------------------------------------------------------------- monte sua análise

function BuilderSection({ initial }: { initial?: AnalysisConfig }) {
  const saved = useSaved();
  const undo = useUndo();
  const [editing, setEditing] = useState<SavedAnalysis | null>(null);
  const [start, setStart] = useState<AnalysisConfig | undefined>(initial);
  const items = (saved.data ?? []).filter((s) => !undo.isHidden(s.id));

  return (
    <>
      <SectionTitle title="Monte sua análise" text="Escolha o que ver, o período, como agrupar, com o que comparar e o tipo de gráfico." />
      <div className="presets">
        {PRESETS.map((p) => (
          <button
            key={p.title}
            type="button"
            className="preset"
            onClick={() => {
              setEditing(null);
              setStart({ ...p.config });
            }}
          >
            <span className="kpi__icon" aria-hidden>
              <Sparkles size={16} />
            </span>
            <span>
              <strong>{p.title}</strong>
              <small>{p.hint}</small>
            </span>
          </button>
        ))}
      </div>
      <Builder initial={start} editing={editing} onEditingDone={() => setEditing(null)} />
      {items.length > 0 && (
        <>
          <div className="section-title">
            <div>
              <h2>Salvas</h2>
              <p>Fixe no Resumo as que quiser ver sempre.</p>
            </div>
          </div>
          <div className="saved-grid">
            {items.map((item) => (
              <SavedCard
                key={item.id}
                item={item}
                onEdit={() => {
                  setEditing(item);
                  setStart({ ...item.config });
                  window.scrollTo({ top: 0, behavior: "smooth" });
                }}
              />
            ))}
          </div>
        </>
      )}
    </>
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
          <div className="table-wrap" tabIndex={0} role="region" aria-label="Tabela da comparação entre os meses">
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
                  <td><strong>Receitas</strong></td>
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
                <span className="stat__label">Receita prevista</span>
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
            <Chart
              type="area"
              labels={points.map((p) => ({ key: p.month, label: p.month }))}
              series={[{ key: "cumulative", name: "Saldo acumulado", color: "var(--accent)", values: points.map((p) => Number(p.cumulative)) }]}
              monthLabels
              description="Saldo acumulado projetado nos próximos meses"
            />
          </section>
          <section className="card">
            <div className="table-wrap" tabIndex={0} role="region" aria-label="Tabela da projeção mês a mês">
              <table className="table">
                <thead>
                  <tr>
                    <th>Mês</th>
                    <th className="num">Receitas</th>
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
  const labels = projection.data.map((p) => ({ key: p.month, label: p.month }));
  const base = cumulativeBalance(months, ZERO_SIM);
  const scenario = cumulativeBalance(months, sim);

  return (
    <div className="stack">
      <p className="muted">
        Simule variações de receita e despesa e compare com {monthLabel(month).toLowerCase()} e
        com a projeção dos próximos 12 meses. Nada aqui altera seus dados.
      </p>
      <section className="card stack">
        <Slider label="Receitas" value={sim.incomePct} min={-50} max={50} onChange={(v) => set({ incomePct: v })} />
        <Slider label="Todas as contas" value={sim.expensePct} min={-50} max={50} onChange={(v) => set({ expensePct: v })} />
        <Slider label="Corte nos gastos não essenciais" value={-sim.cutWantsPct} min={-100} max={0} onChange={(v) => set({ cutWantsPct: -v })} />
        <label className="slider">
          <span>Nova despesa mensal (ex.: financiamento, plano de saúde)</span>
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
            <span className="stat__label">Receitas</span>
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
        <Chart
          type="line"
          labels={labels}
          series={[{ key: "scenario", name: "Com a simulação", color: "var(--accent)", values: scenario }]}
          compare={{ name: "Projeção atual", values: base }}
          monthLabels
          description="Saldo acumulado: projeção atual e com a simulação"
        />
      </section>
    </div>
  );
}

// ---------------------------------------------------------------- página

type SectionKey = "resumo" | "tendencias" | "categorias" | "saude" | "patrimonio" | "comparar" | "projecao" | "simulador" | "calculadoras" | "monte";

const SECTIONS: { key: SectionKey; label: string; group: string; icon: LucideIcon }[] = [
  { key: "resumo", label: "Resumo", group: "Visão geral", icon: LayoutDashboard },
  { key: "tendencias", label: "Tendências", group: "Visão geral", icon: TrendingUp },
  { key: "categorias", label: "Categorias", group: "Visão geral", icon: Tags },
  { key: "saude", label: "Saúde financeira", group: "Visão geral", icon: HeartPulse },
  { key: "patrimonio", label: "Patrimônio e metas", group: "Visão geral", icon: Landmark },
  { key: "comparar", label: "Comparar meses", group: "Ferramentas", icon: GitCompareArrows },
  { key: "projecao", label: "Projeção", group: "Ferramentas", icon: Telescope },
  { key: "simulador", label: "Simulador", group: "Ferramentas", icon: FlaskConical },
  { key: "calculadoras", label: "Calculadoras", group: "Ferramentas", icon: Calculator },
  { key: "monte", label: "Monte sua análise", group: "Personalizar", icon: WandSparkles },
];

// Endereços antigos (?aba=...) continuam funcionando.
const LEGACY: Record<string, SectionKey> = { geral: "resumo", comparar: "comparar", projecao: "projecao", simulador: "simulador" };

export default function Analysis() {
  const [params, setParams] = useSearchParams();
  const requested = params.get("secao") ?? LEGACY[params.get("aba") ?? ""] ?? "resumo";
  const section = (SECTIONS.find((s) => s.key === requested)?.key ?? "resumo") as SectionKey;
  const index = SECTIONS.findIndex((s) => s.key === section);
  const fromLink = params.get("mes");
  const [month, setMonth] = useState(fromLink && /^\d{4}-\d{2}$/.test(fromLink) ? fromLink : thisMonth());
  const [builderStart, setBuilderStart] = useState<AnalysisConfig | undefined>();
  const [direction, setDirection] = useState(0);
  const navRef = useRef<HTMLElement>(null);

  function goTo(next: SectionKey, config?: AnalysisConfig) {
    if (config) setBuilderStart({ ...config });
    setDirection(Math.sign(SECTIONS.findIndex((s) => s.key === next) - index));
    setParams({ secao: next }, { replace: true });
    window.scrollTo({ top: 0 });
  }

  // Mantém a seção ativa visível no seletor do celular.
  useEffect(() => {
    navRef.current?.querySelector('[aria-current="page"]')?.scrollIntoView({ block: "nearest", inline: "center", behavior: prefersReducedMotion() ? "auto" : "smooth" });
  }, [section]);

  let group = "";
  return (
    <div className="stack">
      <PageHeader title="Insights" subtitle="Resultado do mês, tendências, comparações e análises personalizadas." />
      <div className="analysis">
        <nav className="analysis__nav no-print" aria-label="Seções da análise" ref={navRef}>
          {SECTIONS.map((s) => {
            const header = s.group !== group ? <span className="analysis__nav-group">{s.group}</span> : null;
            group = s.group;
            const Icon = s.icon;
            return (
              <Fragment key={s.key}>
                {header}
                <a
                  href={`?secao=${s.key}`}
                  aria-current={s.key === section ? "page" : undefined}
                  onClick={(e) => {
                    e.preventDefault();
                    goTo(s.key);
                  }}
                >
                  <Icon size={16} aria-hidden />
                  {s.label}
                </a>
              </Fragment>
            );
          })}
        </nav>
        <div className="analysis__body page" key={section} data-enter={direction || undefined}>
          {section === "resumo" && <SummarySection month={month} setMonth={setMonth} goTo={goTo} />}
          {section === "tendencias" && <TrendsSection month={month} setMonth={setMonth} />}
          {section === "categorias" && <CategoriesSection month={month} setMonth={setMonth} />}
          {section === "saude" && <HealthSection month={month} setMonth={setMonth} />}
          {section === "patrimonio" && <WealthSection month={month} />}
          {section === "comparar" && (
            <>
              <SectionTitle title="Comparar meses" text="Dois meses lado a lado, categoria por categoria." />
              <CompareTab month={month} />
            </>
          )}
          {section === "projecao" && (
            <>
              <SectionTitle title="Projeção" text="Próximos 12 meses considerando recorrências, parcelas e despesas previstas." />
              <ProjectionTab />
            </>
          )}
          {section === "simulador" && (
            <>
              <SectionTitle title="Simulador" text="Efeito de reduções de despesa ou aumento de receita em 12 meses." />
              <SimulatorTab />
            </>
          )}
          {section === "calculadoras" && (
            <>
              <SectionTitle title="Calculadoras" text="Juros compostos, planejamento, à vista ou parcelado, antecipação de parcelas e reserva de emergência." />
              <Calculators />
            </>
          )}
          {section === "monte" && <BuilderSection initial={builderStart} />}
        </div>
      </div>
    </div>
  );
}
