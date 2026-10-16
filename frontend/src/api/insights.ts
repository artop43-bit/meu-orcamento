import { api } from "./client";

// Consultor financeiro e tendências (tela "Análise financeira").

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
