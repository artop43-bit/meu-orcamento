import type {
  ColumnType,
  CrmDeal,
  DateRangeKey,
  WidgetSeriesItem,
  WidgetType,
} from "../api/crm";
import { money } from "./format";

export const STRATEGY_LABELS: Record<string, string> = {
  tabela_pdf: "Tabela nativa do PDF",
  colunas_texto: "Colunas detectadas no texto",
  linhas_financeiras: "Linhas financeiras / extrato",
  pares_chave_valor: "Fichas campo: valor",
  documento_livre: "Documento narrativo traduzido",
  ocr_tabela: "OCR local · tabela",
  ocr_financeiro: "OCR local · extrato",
  ocr_campos: "OCR local · fichas",
  ocr_texto: "OCR local · documento",
};

export const COLUMN_TYPE_LABELS: Record<ColumnType, string> = {
  text: "Texto",
  currency: "Moeda (R$)",
  number: "Número",
  date: "Data",
  phone: "Telefone",
  email: "E-mail",
  boolean: "Sim / Não",
};

export const WIDGET_TYPE_LABELS: Record<WidgetType, string> = {
  kpi: "Indicador (KPI)",
  bar: "Gráfico de barras",
  line: "Linha / Evolução",
  donut: "Gráfico de rosca",
  funnel: "Funil de etapas",
  table: "Tabela resumida",
};

export const DATE_RANGES: [DateRangeKey, string][] = [
  ["all", "Todo o período"],
  ["7d", "Últimos 7 dias"],
  ["30d", "Últimos 30 dias"],
  ["90d", "Últimos 90 dias"],
  ["month", "Este mês"],
  ["year", "Este ano"],
];

export const SOURCE_KIND_LABELS: Record<string, string> = {
  native_crm: "CRM nativo",
  native_crm_contacts: "CRM nativo",
  native_messaging: "Mensageria ao vivo",
  native_budget: "Orçamento ao vivo",
  native_catalog: "Catálogo ao vivo",
  pdf: "PDF importado",
  csv: "CSV importado",
  api: "API externa",
};

export function strategyLabel(key: string): string {
  return STRATEGY_LABELS[key] ?? "Extração local";
}

export function percentShare(part: number, total: number): number {
  if (!total || total <= 0) return 0;
  return Math.round((part / total) * 1000) / 10;
}

const numFmt = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });

export function formatCrmNumber(value: number | string | null | undefined): string {
  const num = Number(value ?? 0);
  if (Number.isNaN(num)) return "0";
  return numFmt.format(num);
}

export function formatDateBr(iso: string | null | undefined): string {
  if (!iso) return "—";
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (match) return `${match[3]}/${match[2]}/${match[1]}`;
  return iso;
}

/** Valor de um gráfico: moeda (R$) ou número no padrão brasileiro. */
export function formatWidgetValue(value: number, format?: "currency" | "number"): string {
  return format === "currency" ? money(value) : formatCrmNumber(value);
}

const CHART_NAMES: Record<"bar" | "line" | "donut" | "funnel", string> = {
  bar: "Barras",
  line: "Linha",
  donut: "Rosca",
  funnel: "Funil",
};

/**
 * Resumo em texto dos valores do gráfico, lido por leitores de tela
 * (ex.: "Barras: Janeiro R$ 1.200,00; Fevereiro R$ 900,00").
 */
export function widgetAriaLabel(
  type: "bar" | "line" | "donut" | "funnel",
  series: WidgetSeriesItem[],
  format?: "currency" | "number",
  limit = 12,
): string {
  const name = CHART_NAMES[type];
  const items = type === "donut" ? series.filter((s) => s.value > 0) : series;
  if (!items.length) return `${name}: sem dados`;
  const total = items.reduce((acc, s) => acc + s.value, 0);
  const parts = items.slice(0, limit).map((item) => {
    const text = `${item.label} ${formatWidgetValue(item.value, format)}`;
    if (type === "donut") return `${text} (${formatCrmNumber(percentShare(item.value, total))}%)`;
    if (type === "funnel") return `${text} (${item.count} registro(s))`;
    return text;
  });
  const rest = items.length - limit;
  return `${name}: ${parts.join("; ")}${rest > 0 ? `; e mais ${rest}` : ""}`;
}

/** O que mostrar no negócio sobre a receita no Meu Orçamento. */
export function dealBudgetState(deal: Pick<CrmDeal, "status" | "budget_income_id">): "sent" | "can_send" | "hidden" {
  if (deal.budget_income_id) return "sent";
  return deal.status === "won" ? "can_send" : "hidden";
}

/** Pergunta antes de excluir um negócio (mesmo padrão das outras exclusões do app). */
export function dealDeleteConfirmText(deal: Pick<CrmDeal, "title" | "budget_income_id">): string {
  const base = `Excluir o negócio "${deal.title}"? As atividades dele também serão apagadas.`;
  return deal.budget_income_id ? `${base} A receita já lançada continua no Meu Orçamento.` : base;
}

export function formatCrmCell(value: unknown, type: ColumnType): string {
  if (value === null || value === undefined || value === "") return "—";
  if (type === "currency") {
    const num = Number(value);
    return Number.isNaN(num) ? String(value) : money(num);
  }
  if (type === "number") {
    const num = Number(value);
    return Number.isNaN(num) ? String(value) : formatCrmNumber(num);
  }
  if (type === "date") return formatDateBr(String(value));
  if (type === "boolean") return value === true || value === "true" ? "Sim" : "Não";
  return String(value);
}
