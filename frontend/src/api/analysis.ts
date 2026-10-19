import { api } from "./client";

export type ScoreComponent = { key: string; label: string; points: number; max: number; detail: string };

export type Score = {
  score: number | null;
  label: string;
  components: ScoreComponent[];
  tips: string[];
  reserve_total: string;
  reserve_months: number | null;
};

export type Rule = {
  income: string;
  needs: string;
  wants: string;
  savings: string;
  deficit: string;
  needs_pct: number | null;
  wants_pct: number | null;
  savings_pct: number | null;
  needs_ok: boolean;
  wants_ok: boolean;
  savings_ok: boolean;
};

export type Overview = { month: string; score: Score; rule: Rule };

export type CompareTotals = { a: string; b: string; delta: string };

export type Comparison = {
  month_a: string;
  month_b: string;
  income: CompareTotals;
  expenses: CompareTotals;
  balance: CompareTotals;
  categories: {
    category_id: string | null;
    name: string;
    a: string;
    b: string;
    delta: string;
    delta_pct: number | null;
  }[];
};

export type ProjectionPoint = {
  month: string;
  income: string;
  expenses: string;
  planned?: string;
  non_essential: string;
  balance: string;
  cumulative: string;
};

export type InvestmentKind =
  | "poupanca"
  | "renda_fixa"
  | "tesouro"
  | "fundos"
  | "acoes"
  | "fiis"
  | "cripto"
  | "previdencia"
  | "outro";

export const INVESTMENT_KINDS: Record<InvestmentKind, string> = {
  poupanca: "Poupança",
  renda_fixa: "Renda fixa (CDB, LCI, LCA)",
  tesouro: "Tesouro Direto",
  fundos: "Fundos",
  acoes: "Ações",
  fiis: "Fundos imobiliários",
  cripto: "Criptomoedas",
  previdencia: "Previdência",
  outro: "Outro",
};

export type Investment = {
  id: string;
  name: string;
  kind: InvestmentKind;
  institution: string | null;
  invested_amount: string;
  current_value: string;
  is_emergency_reserve: boolean;
  notes: string | null;
  ticker: string | null;
  quantity: string | null;
  updated_at: string;
  return_amount: string;
  return_pct: number | null;
};

export type InvestmentInput = {
  name: string;
  kind: InvestmentKind;
  institution: string | null;
  invested_amount: string;
  current_value: string;
  is_emergency_reserve: boolean;
  ticker?: string | null;
  quantity?: string | null;
};

type IndicatorValue = { value: number; date: string } | null;

export type Indicators = {
  available: boolean;
  selic: IndicatorValue;
  cdi: IndicatorValue;
  ipca_12m: IndicatorValue;
  fetched_at: string;
};

export const analysisApi = {
  overview: (month: string) => api.get<Overview>(`/analysis/overview?month=${month}`),
  compare: (a: string, b: string) => api.get<Comparison>(`/analysis/compare?a=${a}&b=${b}`),
  projection: (start: string, months = 12) =>
    api.get<ProjectionPoint[]>(`/analysis/projection?start=${start}&months=${months}`),

  investments: () => api.get<Investment[]>("/investments"),
  createInvestment: (data: InvestmentInput) => api.post<Investment>("/investments", data),
  updateInvestment: (id: string, data: Partial<InvestmentInput>) =>
    api.patch<Investment>(`/investments/${id}`, data),
  deleteInvestment: (id: string) => api.delete(`/investments/${id}`),
  indicators: () => api.get<Indicators>("/indicators"),
};
