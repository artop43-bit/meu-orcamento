import { api } from "./client";

// Insights do mês e tendências (tela Insights).

export type InsightTone = "praise" | "info" | "warning" | "danger";
export type InsightMessage = { tone: InsightTone; title: string; text: string; category_id?: string | null };

export type Insights = {
  month: string;
  mood: "great" | "good" | "attention" | "concern" | "empty";
  headline: string;
  summary: string;
  savings_pct: number | null;
  in_progress: boolean;
  messages: InsightMessage[];
  alerts: InsightMessage[];
};

export type TrendPoint = {
  month: string;
  income: string;
  expenses: string;
  balance: string;
  savings_pct: number | null;
  has_data: boolean;
};

type AverageKey = "income_3m" | "expenses_3m" | "balance_3m" | "income_6m" | "expenses_6m" | "balance_6m";

export type Trends = {
  months: TrendPoint[];
  categories: { category_id: string | null; name: string; color: string | null; totals: string[] }[];
  averages: Record<AverageKey, string | null>;
  current: TrendPoint;
  same_month_last_year: TrendPoint;
  wealth: { invested: string; current: string; return_value: string; reserve: string };
  goals: { count: number; target: string; saved: string };
};

export const insightsApi = {
  insights: (month: string) => api.get<Insights>(`/analysis/insights?month=${month}`),
  trends: (until: string, months = 12) => api.get<Trends>(`/analysis/trends?until=${until}&months=${months}`),
};

// ---------------------------------------------------------------- monte sua análise

export type Metric = "expenses" | "income" | "balance" | "savings_rate" | "investments";
export type Period = "3m" | "6m" | "12m" | "24m" | "custom";
export type Group = "month" | "month_category" | "month_type" | "category" | "type" | "kind";
export type Compare = "none" | "previous" | "last_year" | "average";
export type ChartKind = "bar" | "stacked" | "line" | "area" | "donut" | "hbar" | "table";

export type AnalysisConfig = {
  metric: Metric;
  period: Period;
  start?: string | null;
  end?: string | null;
  group: Group;
  categories: string[];
  compare: Compare;
  chart: ChartKind;
};

export type SeriesResult = {
  labels: { key: string; label: string; color?: string | null }[];
  series: { key: string; name: string; color: string | null; values: (number | null)[] }[];
  compare: { name: string; values: (number | null)[] } | null;
  unit: "money" | "percent";
  total: number | null;
  compare_total: number | null;
  start: string;
  end: string;
};

export type SavedAnalysis = { id: string; name: string; config: AnalysisConfig; pinned: boolean; position: number };

export const builderApi = {
  series: (config: AnalysisConfig) => api.post<SeriesResult>("/analysis/series", config),
  saved: () => api.get<SavedAnalysis[]>("/analysis/saved"),
  save: (data: { name: string; config: AnalysisConfig; pinned: boolean }) => api.post<SavedAnalysis>("/analysis/saved", data),
  update: (id: string, data: Partial<{ name: string; config: AnalysisConfig; pinned: boolean }>) =>
    api.patch<SavedAnalysis>(`/analysis/saved/${id}`, data),
  remove: (id: string) => api.delete(`/analysis/saved/${id}`),
};

// ---------------------------------------------------------------- tire sua dúvida (v1.7 / v1.7.5)

export type AskItem = { label: string; detail: string | null; value: string | null; link: string | null };
export type AskAnswer = {
  intent: string;
  answer: string;
  items: AskItem[];
  links: { label: string; to: string }[];
  suggestions: string[];
  /** Devolvido na pergunta seguinte para "e em setembro?" continuar o assunto. */
  context?: Record<string, unknown> | null;
  /** Conversa guardada (null com o histórico desligado). */
  conversation_id?: string | null;
};
export type AskConversation = { id: string; title: string; updated_at: string };
export type AskMessage = { id: string; question: string; answer: AskAnswer; created_at: string };

export const ASK_CONVERSATIONS_KEY = ["ask", "conversations"] as const;

export const askApi = {
  ask: (question: string, conversationId?: string | null, context?: AskAnswer["context"]) =>
    api.post<AskAnswer>("/ask", { question, conversation_id: conversationId ?? null, context: context ?? null }),
  conversations: () => api.get<AskConversation[]>("/ask/conversations"),
  messages: (id: string) => api.get<AskMessage[]>(`/ask/conversations/${id}`),
  remove: (id: string) => api.delete(`/ask/conversations/${id}`),
  removeAll: () => api.delete("/ask/conversations"),
  setHistory: (history: boolean) => api.patch<{ history: boolean }>("/ask/settings", { history }),
};
