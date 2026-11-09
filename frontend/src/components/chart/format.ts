import { getPrefs } from "../../lib/prefs";
import { money } from "../../lib/format";

export type ChartType = "bar" | "stacked" | "line" | "area" | "donut" | "hbar" | "table";
export type ChartUnit = "money" | "percent";

/**
 * Paleta para séries sem cor própria (v1.6): a 1ª segue a cor de destaque escolhida; as demais
 * são tokens do tema (--chart-1 a --chart-8), com versão própria no claro e no escuro.
 */
export const PALETTE = ["var(--accent)", ...Array.from({ length: 8 }, (_, i) => `var(--chart-${i + 1})`)];

export function colorFor(color: string | null | undefined, index: number): string {
  return color || PALETTE[index % PALETTE.length];
}

export function formatValue(value: number | null | undefined, unit: ChartUnit): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (unit === "percent") return `${value.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
  return money(value);
}

/** Valor curto para eixos e para o centro da rosca: "R$ 2,3 mil", "R$ 850", "12%". */
export function compactValue(value: number, unit: ChartUnit): string {
  if (unit === "percent") return `${Math.round(value)}%`;
  if (getPrefs().privacy) return "R$ ••";
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (abs >= 1_000_000) return `${sign}R$ ${(abs / 1_000_000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} mi`;
  if (abs >= 1000) return `${sign}R$ ${(abs / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} mil`;
  return `${sign}R$ ${Math.round(abs)}`;
}

/** Quais gráficos fazem sentido para cada agrupamento. */
export function chartsFor(group: string, seriesCount: number): ChartType[] {
  if (group === "category" || group === "type" || group === "kind") return ["hbar", "donut", "bar", "table"];
  if (seriesCount > 1) return ["stacked", "bar", "line", "area", "table"];
  return ["bar", "line", "area", "table"];
}

export const CHART_NAMES: Record<ChartType, string> = {
  bar: "Barras",
  stacked: "Barras empilhadas",
  line: "Linhas",
  area: "Área",
  donut: "Rosca",
  hbar: "Ranking",
  table: "Tabela",
};

/** Passo "redondo" (1, 2, 2,5 ou 5 × 10^n) para a régua ter números fáceis de ler. */
export function niceStep(raw: number): number {
  if (raw <= 0) return 1;
  const exp = Math.pow(10, Math.floor(Math.log10(raw)));
  const n = raw / exp;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * exp;
}

/** Régua de um gráfico: mínimo, máximo e marcas, sempre incluindo o zero. */
export function niceScale(low: number, high: number): { min: number; max: number; ticks: number[] } {
  const lo = Math.min(0, low);
  const hi = Math.max(0, high);
  const step = niceStep((hi - lo) / 4 || 1);
  const max = Math.ceil(hi / step) * step || step;
  const min = Math.floor(lo / step) * step;
  const ticks: number[] = [];
  for (let v = min; v <= max + step / 2; v += step) ticks.push(Math.round(v * 100) / 100);
  return { min, max, ticks };
}
