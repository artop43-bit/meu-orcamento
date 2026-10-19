import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bookmark,
  ChartArea,
  ChartBarDecreasing,
  ChartColumn,
  ChartColumnStacked,
  ChartLine,
  ChartPie,
  ChevronDown,
  Pencil,
  Pin,
  PinOff,
  Save,
  Table2,
  Trash2,
  type LucideIcon,
} from "lucide-react";
import { useNavigate } from "react-router";

import { useCategories, type Category } from "../api/budget";
import { errorMessage } from "../api/client";
import { builderApi, type AnalysisConfig, type ChartKind, type Compare, type Group, type Metric, type Period, type SavedAnalysis } from "../api/insights";
import { monthLabel, thisMonth, addMonths } from "../lib/format";
import { announce } from "../lib/announce";
import { Chart } from "./chart/Chart";
import { CHART_NAMES, chartsFor, formatValue } from "./chart/format";
import { Alert, Button, LoadingRegion, Sheet, Skeleton } from "./ui";
import { useUndo } from "./undo";
import { DateField } from "./DateField";

// ---------------------------------------------------------------- opções

export const DEFAULT_CONFIG: AnalysisConfig = {
  metric: "expenses",
  period: "6m",
  group: "month",
  categories: [],
  compare: "none",
  chart: "bar",
};

const METRICS: [Metric, string][] = [
  ["expenses", "Gastos"],
  ["income", "Receitas"],
  ["balance", "Sobra"],
  ["savings_rate", "Taxa de poupança"],
  ["investments", "Patrimônio"],
];

const PERIODS: [Period, string][] = [
  ["3m", "3 meses"],
  ["6m", "6 meses"],
  ["12m", "12 meses"],
  ["24m", "24 meses"],
  ["custom", "Escolher datas"],
];

const GROUPS: [Group, string][] = [
  ["month", "Por mês"],
  ["month_category", "Mês × categoria"],
  ["month_type", "Mês × essencial"],
  ["category", "Por categoria"],
  ["type", "Essencial × não essencial"],
];

const COMPARES: [Compare, string][] = [
  ["none", "Sem comparação"],
  ["previous", "Período anterior"],
  ["last_year", "Ano passado"],
  ["average", "Minha média"],
];

const CHART_ICONS: Record<ChartKind, LucideIcon> = {
  bar: ChartColumn,
  stacked: ChartColumnStacked,
  line: ChartLine,
  area: ChartArea,
  donut: ChartPie,
  hbar: ChartBarDecreasing,
  table: Table2,
};

/** Combinações prontas para começar (o usuário ajusta depois). */
export const PRESETS: { title: string; hint: string; config: AnalysisConfig }[] = [
  {
    title: "Onde gastei no ano",
    hint: "Ranking das categorias em 12 meses",
    config: { ...DEFAULT_CONFIG, period: "12m", group: "category", chart: "hbar" },
  },
  {
    title: "Categorias mês a mês",
    hint: "Barras empilhadas dos últimos 6 meses",
    config: { ...DEFAULT_CONFIG, group: "month_category", chart: "stacked" },
  },
  {
    title: "Minha taxa de poupança",
    hint: "Percentual da receita poupado em 12 meses",
    config: { ...DEFAULT_CONFIG, metric: "savings_rate", period: "12m", chart: "line" },
  },
  {
    title: "Gastos × ano passado",
    hint: "Mesmos meses, um ano antes",
    config: { ...DEFAULT_CONFIG, compare: "last_year", chart: "bar" },
  },
  {
    title: "Essencial × não essencial",
    hint: "Necessidades e desejos em 6 meses",
    config: { ...DEFAULT_CONFIG, group: "type", chart: "donut" },
  },
  {
    title: "Onde está meu dinheiro",
    hint: "Patrimônio por tipo de investimento",
    config: { ...DEFAULT_CONFIG, metric: "investments", group: "kind", compare: "none", chart: "donut" },
  },
];

/** Mantém a configuração coerente (ex.: renda só por mês; gráfico compatível com o agrupamento). */
export function normalize(config: AnalysisConfig): AnalysisConfig {
  const next = { ...config };
  if (next.metric === "investments") {
    next.group = "kind";
    next.compare = "none";
    next.categories = [];
  } else if (next.metric !== "expenses") {
    next.group = "month";
    next.categories = [];
  } else if (next.group === "kind") {
    next.group = "month";
  }
  if (next.period === "custom") {
    next.end = next.end || thisMonth();
    next.start = next.start || addMonths(next.end, -5);
  } else {
    next.start = null;
    next.end = null;
  }
  const multi = next.group === "month_category" || next.group === "month_type";
  const allowed = chartsFor(next.group, multi ? 2 : 1);
  if (!allowed.includes(next.chart)) next.chart = allowed[0];
  return next;
}

function label<T extends string>(options: [T, string][], value: T): string {
  return options.find(([key]) => key === value)?.[1] ?? value;
}

export function describe(config: AnalysisConfig, categories: Category[]): string {
  const metric = label(METRICS, config.metric);
  const group = config.metric === "investments" ? "por tipo" : label(GROUPS, config.group).toLowerCase();
  const period =
    config.metric === "investments"
      ? "hoje"
      : config.period === "custom"
        ? `de ${monthLabel(config.start ?? thisMonth(), true)} a ${monthLabel(config.end ?? thisMonth(), true)}`
        : `últimos ${label(PERIODS, config.period)}`;
  const names = config.categories
    .map((id) => categories.find((c) => c.id === id)?.name)
    .filter(Boolean)
    .join(", ");
  return `${metric}${names ? ` (${names})` : ""} ${group} · ${period}`;
}

// ---------------------------------------------------------------- resultado (gráfico)

export function useSeries(config: AnalysisConfig) {
  return useQuery({
    queryKey: ["budget", "series", config],
    queryFn: () => builderApi.series(config),
    placeholderData: keepPreviousData,
  });
}

export function AnalysisResult({ config, title, height, actions }: { config: AnalysisConfig; title: string; height?: number; actions?: ReactNode }) {
  const result = useSeries(config);
  const navigate = useNavigate();
  const data = result.data;
  // Pelos dados recebidos (e não pela configuração): enquanto o novo resultado carrega, o anterior
  // continua na tela e pode ter outro agrupamento.
  const monthGroup = Boolean(data?.labels.length) && /^\d{4}-\d{2}$/.test(data?.labels[0].key ?? "");
  const delta = data && data.total !== null && data.compare_total ? ((data.total - data.compare_total) / Math.abs(data.compare_total)) * 100 : null;
  // Para gastos, subir é ruim; para renda, sobra e poupança, subir é bom.
  const upIsGood = config.metric !== "expenses";

  return (
    <section className="card stack" aria-busy={result.isFetching || undefined}>
      <div className="builder__result-head">
        <div>
          <h3 className="builder__title">{title}</h3>
          {data && data.total !== null && (
            <div className="row" style={{ gap: 10, alignItems: "baseline" }}>
              <span className="builder__total">{formatValue(data.total, data.unit)}</span>
              <span className="muted small">{data.unit === "percent" ? "média no período" : "no período"}</span>
              {delta !== null && Number.isFinite(delta) && (
                <span className={`small ${Math.abs(delta) < 1 ? "muted" : delta > 0 === upIsGood ? "tone--ok" : "tone--error"}`}>
                  {delta > 0 ? "+" : ""}
                  {Math.round(delta)}% vs {data.compare?.name.toLowerCase()}
                </span>
              )}
            </div>
          )}
        </div>
        {actions}
      </div>
      {result.isPending && (
        <LoadingRegion label="Montando o gráfico">
          <Skeleton height={height ?? 260} />
        </LoadingRegion>
      )}
      {result.isError && <Alert tone="error">{errorMessage(result.error)}</Alert>}
      {data && data.labels.length === 0 && <p className="muted">Nada para mostrar com esses filtros.</p>}
      {data && data.labels.length > 0 && (
        <div className={result.isPlaceholderData ? "is-stale" : undefined}>
          <Chart
            type={config.chart}
            labels={data.labels}
            series={data.series}
            compare={data.compare}
            unit={data.unit}
            monthLabels={monthGroup}
            height={height}
            description={title}
            onSelect={monthGroup ? (key) => navigate(`/orcamento/${key}`) : undefined}
          />
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------- controles

function Choices<T extends string>({
  name,
  options,
  value,
  onChange,
  disabled,
}: {
  name: string;
  options: [T, string][];
  value: T;
  onChange: (v: T) => void;
  disabled?: (v: T) => boolean;
}) {
  return (
    <div className="choices" role="radiogroup">
      {options.map(([key, text]) => (
        <label key={key} className="choice">
          <input type="radio" name={name} checked={value === key} disabled={disabled?.(key)} onChange={() => onChange(key)} />
          <span>{text}</span>
        </label>
      ))}
    </div>
  );
}

export function ChartTypePicker({ config, onChange, idPrefix }: { config: AnalysisConfig; onChange: (c: AnalysisConfig) => void; idPrefix: string }) {
  const multi = config.group === "month_category" || config.group === "month_type";
  return (
    <div className="chart-types" role="radiogroup" aria-label="Tipo de gráfico">
      {chartsFor(config.group, multi ? 2 : 1).map((type) => {
        const Icon = CHART_ICONS[type];
        return (
          <label key={type} title={CHART_NAMES[type]}>
            <input type="radio" name={`${idPrefix}-chart`} checked={config.chart === type} onChange={() => onChange({ ...config, chart: type })} aria-label={CHART_NAMES[type]} />
            <span>
              <Icon size={18} aria-hidden />
            </span>
          </label>
        );
      })}
    </div>
  );
}

type Part = "metric" | "period" | "group" | "categories" | "compare";

function Control({ part, config, set, categories, idPrefix }: { part: Part; config: AnalysisConfig; set: (c: Partial<AnalysisConfig>) => void; categories: Category[]; idPrefix: string }) {
  const expenses = config.metric === "expenses";
  if (part === "metric")
    return <Choices name={`${idPrefix}-metric`} options={METRICS} value={config.metric} onChange={(metric) => set({ metric })} />;
  if (part === "period")
    return (
      <div className="stack stack--tight">
        <Choices name={`${idPrefix}-period`} options={PERIODS} value={config.period} onChange={(period) => set({ period })} disabled={() => config.metric === "investments"} />
        {config.period === "custom" && (
          <div className="grid-2">
            <label className="month-picker">
              De
              <DateField month value={config.start ?? ""} onChange={(v) => v && set({ start: v })} />
            </label>
            <label className="month-picker">
              Até
              <DateField month value={config.end ?? ""} onChange={(v) => v && set({ end: v })} />
            </label>
          </div>
        )}
      </div>
    );
  if (part === "group")
    return <Choices name={`${idPrefix}-group`} options={GROUPS} value={config.group} onChange={(group) => set({ group })} disabled={(g) => !expenses && g !== "month"} />;
  if (part === "compare")
    return <Choices name={`${idPrefix}-compare`} options={COMPARES} value={config.compare} onChange={(compare) => set({ compare })} disabled={() => config.metric === "investments"} />;
  return (
    <div className="choices">
      {categories.map((c) => (
        <label key={c.id} className="choice">
          <input
            type="checkbox"
            checked={config.categories.includes(c.id)}
            disabled={!expenses}
            onChange={(e) => set({ categories: e.target.checked ? [...config.categories, c.id] : config.categories.filter((id) => id !== c.id) })}
          />
          <span>
            <i className="dot" style={{ background: c.color ?? undefined }} aria-hidden /> {c.name}
          </span>
        </label>
      ))}
    </div>
  );
}

const PART_TITLES: Record<Part, string> = {
  metric: "O que analisar",
  period: "Período",
  group: "Como agrupar",
  categories: "Categorias (opcional)",
  compare: "Comparar com",
};

function chipValue(part: Part, config: AnalysisConfig, categories: Category[]): string {
  if (part === "metric") return label(METRICS, config.metric);
  if (part === "period") return config.metric === "investments" ? "Hoje" : config.period === "custom" ? `${monthLabel(config.start ?? thisMonth(), true)} – ${monthLabel(config.end ?? thisMonth(), true)}` : label(PERIODS, config.period);
  if (part === "group") return config.metric === "investments" ? "Por tipo" : label(GROUPS, config.group);
  if (part === "compare") return label(COMPARES, config.compare);
  if (config.categories.length === 0) return "Todas as categorias";
  if (config.categories.length === 1) return categories.find((c) => c.id === config.categories[0])?.name ?? "1 categoria";
  return `${config.categories.length} categorias`;
}

// ---------------------------------------------------------------- construtor

export function Builder({ initial, editing, onEditingDone }: { initial?: AnalysisConfig; editing?: SavedAnalysis | null; onEditingDone?: () => void }) {
  const categories = useCategories().data ?? [];
  const [config, setConfig] = useState<AnalysisConfig>(() => normalize(initial ?? DEFAULT_CONFIG));
  const [sheet, setSheet] = useState<Part | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (initial) setConfig(normalize(initial));
  }, [initial]);

  const set = (patch: Partial<AnalysisConfig>) => setConfig((c) => normalize({ ...c, ...patch }));
  const parts: Part[] = config.metric === "expenses" ? ["metric", "period", "group", "categories", "compare"] : ["metric", "period", "group", "compare"];
  const title = useMemo(() => describe(config, categories), [config, categories]);

  return (
    <div className="builder">
      <aside className="builder__panel builder__panel--desktop card" aria-label="Filtros da análise">
        {parts.map((part) => (
          <fieldset key={part} className="control">
            <legend>{PART_TITLES[part]}</legend>
            <Control part={part} config={config} set={set} categories={categories} idPrefix="d" />
          </fieldset>
        ))}
      </aside>

      <div className="stack" style={{ gap: 14, minWidth: 0 }}>
        <div className="filter-chips" role="toolbar" aria-label="Filtros da análise">
          {parts.map((part) => (
            <button key={part} type="button" className="filter-chip" onClick={() => setSheet(part)} aria-haspopup="dialog">
              <small>{PART_TITLES[part].replace(" (opcional)", "")}:</small> {chipValue(part, config, categories)}
              <ChevronDown size={14} aria-hidden />
            </button>
          ))}
        </div>

        <div className="row" style={{ justifyContent: "space-between" }}>
          <ChartTypePicker config={config} onChange={setConfig} idPrefix="b" />
          <span className="row" style={{ gap: 8 }}>
            {editing && (
              <Button type="button" variant="secondary" onClick={onEditingDone}>
                Cancelar edição
              </Button>
            )}
            <Button type="button" onClick={() => setSaving(true)}>
              <Save size={16} /> {editing ? "Salvar alterações" : "Salvar análise"}
            </Button>
          </span>
        </div>

        <AnalysisResult config={config} title={title} height={300} />
      </div>

      <Sheet open={sheet !== null} title={sheet ? PART_TITLES[sheet] : ""} onClose={() => setSheet(null)}>
        {sheet && (
          <div className="stack">
            <Control part={sheet} config={config} set={set} categories={categories} idPrefix="m" />
            <Button type="button" block onClick={() => setSheet(null)}>
              Ver resultado
            </Button>
          </div>
        )}
      </Sheet>

      <Sheet open={saving} title={editing ? "Salvar alterações" : "Salvar análise"} onClose={() => setSaving(false)}>
        {saving && (
          <SaveForm
            config={config}
            suggested={editing?.name ?? title.split(" · ")[0]}
            editing={editing ?? null}
            onDone={() => {
              setSaving(false);
              onEditingDone?.();
            }}
          />
        )}
      </Sheet>
    </div>
  );
}

function SaveForm({ config, suggested, editing, onDone }: { config: AnalysisConfig; suggested: string; editing: SavedAnalysis | null; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(suggested.slice(0, 60));
  const [pinned, setPinned] = useState(editing?.pinned ?? true);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      if (editing) await builderApi.update(editing.id, { name, config, pinned });
      else await builderApi.save({ name, config, pinned });
      await queryClient.invalidateQueries({ queryKey: SAVED_KEY });
      announce(pinned ? "Análise salva e fixada no Resumo" : "Análise salva");
      onDone();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <form className="form" onSubmit={submit}>
      <Alert tone="error">{error}</Alert>
      <label>
        Nome
        <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={60} autoFocus />
      </label>
      <label className="check">
        <input type="checkbox" checked={pinned} onChange={(e) => setPinned(e.target.checked)} />
        Fixar no Resumo de Insights
      </label>
      <div className="form-actions">
        <Button type="button" variant="secondary" onClick={onDone}>
          Cancelar
        </Button>
        <Button type="submit" loading={loading}>
          <Bookmark size={16} /> Salvar
        </Button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------- análises salvas

export const SAVED_KEY = ["budget", "saved-analyses"] as const;

export function useSaved() {
  return useQuery({ queryKey: SAVED_KEY, queryFn: builderApi.saved });
}

export function SavedCard({ item, onEdit, compact }: { item: SavedAnalysis; onEdit?: () => void; compact?: boolean }) {
  const queryClient = useQueryClient();
  const undo = useUndo();

  async function togglePin() {
    await builderApi.update(item.id, { pinned: !item.pinned });
    await queryClient.invalidateQueries({ queryKey: SAVED_KEY });
    announce(item.pinned ? "Removida do Resumo" : "Fixada no Resumo");
  }

  return (
    <AnalysisResult
      config={item.config}
      title={item.name}
      height={compact ? 200 : 240}
      actions={
        <span className="row" style={{ gap: 0 }}>
          {onEdit && (
            <button type="button" className="icon-btn" aria-label={`Editar ${item.name}`} title="Editar" onClick={onEdit}>
              <Pencil size={16} />
            </button>
          )}
          <button type="button" className="icon-btn" aria-label={item.pinned ? `Tirar ${item.name} do Resumo` : `Fixar ${item.name} no Resumo`} title={item.pinned ? "Tirar do Resumo" : "Fixar no Resumo"} onClick={togglePin}>
            {item.pinned ? <PinOff size={16} /> : <Pin size={16} />}
          </button>
          <button
            type="button"
            className="icon-btn"
            aria-label={`Excluir ${item.name}`}
            title="Excluir"
            onClick={() =>
              undo.remove({
                ids: [item.id],
                message: `"${item.name}" excluída`,
                commit: async () => {
                  await builderApi.remove(item.id);
                  await queryClient.invalidateQueries({ queryKey: SAVED_KEY });
                },
              })
            }
          >
            <Trash2 size={16} />
          </button>
        </span>
      }
    />
  );
}
