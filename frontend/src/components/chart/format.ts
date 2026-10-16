import { money } from "../../lib/format";

export type ChartType = "bar" | "stacked" | "line" | "area" | "donut" | "hbar" | "table";
export type ChartUnit = "money" | "percent";

/** Paleta para séries sem cor própria (boa leitura em claro e escuro). */
export const PALETTE = ["#1f9d7a", "#e8833a", "#4e79a7", "#b07aa1", "#e15759", "#76b7b2", "#edc948", "#9c755f", "#bab0ac"];

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
