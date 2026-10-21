import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";

export type Category = {
  id: string;
  name: string;
  is_essential: boolean;
  color: string | null;
  monthly_limit: string | null;
  /** v1.3: a sobra do limite passa para o mês seguinte. */
  carry_over?: boolean;
  carry_since?: string | null;
  /** v1.4: dedutível no Imposto de Renda. */
  deductible?: Deductible | null;
};

export type Deductible = "saude" | "educacao" | "previdencia" | "pensao";
export const DEDUCTIBLE_LABEL: Record<Deductible, string> = {
  saude: "Saúde",
  educacao: "Educação",
  previdencia: "Previdência privada (PGBL)",
  pensao: "Pensão alimentícia",
};

export type IncomeType = "fixed" | "variable";
export type PaymentMethod = "pix" | "debit" | "credit" | "boleto" | "cash";
export type Interval = 1 | 2 | 3 | 6 | 12;

export const PAYMENT_METHODS: { value: PaymentMethod; label: string }[] = [
  { value: "pix", label: "Pix" },
  { value: "debit", label: "Débito" },
  { value: "credit", label: "Crédito" },
  { value: "boleto", label: "Boleto" },
  { value: "cash", label: "Dinheiro" },
];

export const INTERVALS: { value: Interval; label: string }[] = [
  { value: 1, label: "Todo mês" },
  { value: 2, label: "A cada 2 meses" },
  { value: 3, label: "A cada 3 meses" },
  { value: 6, label: "A cada 6 meses" },
  { value: 12, label: "Uma vez por ano" },
];

export function paymentLabel(value: string | null | undefined): string | null {
  return PAYMENT_METHODS.find((p) => p.value === value)?.label ?? null;
}

export type Income = {
  id: string;
  month: string;
  description: string;
  amount: string;
  income_type: IncomeType;
  day: number | null;
  notes: string | null;
  account_id: string | null;
  recurring_id: string | null;
  /** v1.4: faturamento do MEI. */
  mei?: boolean;
};

export type Expense = {
  id: string;
  month: string;
  description: string;
  amount: string;
  category_id: string | null;
  due_date: string | null;
  paid: boolean;
  paid_at: string | null;
  notes: string | null;
  payment_method: PaymentMethod | null;
  card_id: string | null;
  purchase_date: string | null;
  debit_card_id?: string | null;
  receipt_ids?: string[];
  account_id: string | null;
  needs_review: boolean;
  installment_group_id: string | null;
  installment_number: number | null;
  installment_total: number | null;
  recurring_id: string | null;
  /** v1.3: parte de uma compra dividida em categorias. */
  split_group_id?: string | null;
};

export type CategoryTotal = {
  limit?: string | null;
  limit_pct?: number | null;
  /** v1.3: parte do limite que veio da sobra dos meses anteriores. */
  limit_carried?: string | null;
  category_id: string | null;
  name: string;
  is_essential: boolean;
  total: string;
};

export type MonthSummary = {
  income_total: string;
  expense_total: string;
  paid_total: string;
  pending_total: string;
  balance: string;
  committed_pct: number | null;
  essential_total: string;
  non_essential_total: string;
  by_category: CategoryTotal[];
};

export type MonthData = {
  month: string;
  incomes: Income[];
  expenses: Expense[];
  summary: MonthSummary;
};

export type Recurring = {
  id: string;
  kind: "income" | "expense";
  description: string;
  amount: string;
  category_id: string | null;
  due_day: number | null;
  start_month: string;
  end_month: string | null;
  interval_months: Interval;
  income_type: IncomeType | null;
  payment_method: PaymentMethod | null;
  notes: string | null;
};

export type GoalKind =
  | "emergency"
  | "purchase"
  | "travel"
  | "health"
  | "education"
  | "home"
  | "vehicle"
  | "debt"
  | "retirement"
  | "other";

export type GoalProjection = {
  status: "completed" | "on_track" | "ahead" | "behind" | "estimate" | "no_pace";
  remaining: string;
  pace: string | null;
  pace_source: "contributions" | "plan" | "surplus" | null;
  eta: string | null;
  months_needed: number | null;
  required_monthly: string | null;
  months_left: number | null;
};

export type Goal = {
  id: string;
  name: string;
  target_amount: string;
  current_amount: string;
  target_date: string | null;
  progress_pct: number;
  kind: GoalKind;
  motivation: string | null;
  monthly_plan: string | null;
  is_main: boolean;
  completed_at: string | null;
  image_id: string | null;
  projection: GoalProjection | null;
};

export type GoalInput = {
  name: string;
  target_amount: string;
  current_amount?: string;
  target_date?: string | null;
  kind?: GoalKind;
  motivation?: string | null;
  monthly_plan?: string | null;
  is_main?: boolean;
};

export type GoalSuggestion = { goal_id: string; goal_name: string; surplus: string; amount: string };

export type HistoryPoint = {
  month: string;
  income: string;
  expenses: string;
  paid: string;
  balance: string;
  committed_pct: number | null;
  has_data: boolean;
};

export type DeleteScope = "one" | "following";
export type EditScope = DeleteScope;

export type ExpenseInput = {
  description: string;
  amount: string;
  category_id?: string | null;
  due_date?: string | null;
  notes?: string | null;
  installments?: number | null;
  paid?: boolean;
  payment_method?: PaymentMethod | null;
  amount_mode?: "parcel" | "total";
  repeat?: boolean;
  interval_months?: Interval;
  until_month?: string | null;
  card_id?: string | null;
  purchase_date?: string | null;
  debit_card_id?: string | null;
  account_id?: string | null;
  /** v1.3: compra dividida em categorias (a soma das partes é igual ao valor). */
  parts?: { category_id: string; amount: string }[] | null;
  /** v1.3: identificador do aparelho (lançamento sem internet, sem duplicar no reenvio). */
  client_ref?: string;
};

/** Leitura da foto de um comprovante (v1.3). */
export type ReceiptReading = {
  kind: "boleto" | "cupom" | "desconhecido";
  amount: string | null;
  date: string | null;
  description: string | null;
};

export type IncomeInput = {
  description: string;
  amount: string;
  income_type?: IncomeType;
  day?: number | null;
  notes?: string | null;
  repeat?: "once" | "monthly" | "period";
  until_month?: string | null;
  account_id?: string | null;
  client_ref?: string;
  mei?: boolean;
};

export type Planned = {
  id: string;
  date: string;
  description: string;
  amount: string;
  category_id: string | null;
  notes: string | null;
  expense_id: string | null;
};

export type PlannedInput = Omit<Planned, "id" | "expense_id">;

export type CalendarKind = "expense" | "installment" | "recurring" | "income" | "planned" | "invoice" | "invoice_close";

export type CalendarEvent = {
  id: string;
  date: string | null;
  kind: CalendarKind;
  description: string;
  amount: string;
  paid: boolean | null;
  category_id: string | null;
  category: string | null;
  color: string | null;
  installment_number: number | null;
  installment_total: number | null;
  income_type: IncomeType | null;
  expense_id: string | null;
  notes: string | null;
};

export type CategorySuggestion = { category_id: string; name: string; source: "rule" | "history" | "keywords" };

export type DescriptionSuggestion = {
  description: string;
  amount: string;
  category_id: string | null;
  payment_method: PaymentMethod | null;
  count: number;
};

export type RecurringInput = {
  kind: "income" | "expense";
  description: string;
  amount: string;
  category_id?: string | null;
  due_day?: number | null;
  start_month: string;
  end_month?: string | null;
  interval_months?: Interval;
  income_type?: IncomeType | null;
  payment_method?: PaymentMethod | null;
  notes?: string | null;
};

export const budgetApi = {
  month: (month: string) => api.get<MonthData>(`/months/${month}`),
  history: (months = 12, until?: string) =>
    api.get<HistoryPoint[]>(`/history?months=${months}${until ? `&until=${until}` : ""}`),

  categories: () => api.get<Category[]>("/categories"),
  createCategory: (data: Omit<Category, "id">) => api.post<Category>("/categories", data),
  updateCategory: (id: string, data: Partial<Omit<Category, "id">>) =>
    api.patch<Category>(`/categories/${id}`, data),
  deleteCategory: (id: string) => api.delete(`/categories/${id}`),

  createIncome: (month: string, data: IncomeInput) => api.post<Income>(`/months/${month}/incomes`, data),
  updateIncome: (
    id: string,
    data: Partial<Omit<IncomeInput, "repeat" | "until_month">>,
    scope: EditScope = "one",
  ) => api.patch<Income>(`/incomes/${id}?scope=${scope}`, data),
  deleteIncome: (id: string, scope: DeleteScope = "one") =>
    api.delete(`/incomes/${id}?scope=${scope}`),

  createExpense: (month: string, data: ExpenseInput) =>
    api.post<Expense[]>(`/months/${month}/expenses`, data),
  updateExpense: (id: string, data: Partial<ExpenseInput & { paid: boolean }>, scope: EditScope = "one") =>
    api.patch<Expense>(`/expenses/${id}?scope=${scope}`, data),
  deleteExpense: (id: string, scope: DeleteScope = "one") =>
    api.delete(`/expenses/${id}?scope=${scope}`),

  recurring: () => api.get<Recurring[]>("/recurring"),
  createRecurring: (data: RecurringInput) => api.post<Recurring>("/recurring", data),
  updateRecurring: (id: string, data: Partial<Omit<RecurringInput, "kind" | "start_month">>) =>
    api.patch<Recurring>(`/recurring/${id}`, data),
  deleteRecurring: (id: string) => api.delete(`/recurring/${id}`),

  goals: () => api.get<Goal[]>("/goals"),
  createGoal: (data: GoalInput) => api.post<Goal>("/goals", data),
  updateGoal: (id: string, data: Partial<GoalInput>) => api.patch<Goal>(`/goals/${id}`, data),
  goalSuggestion: () => api.get<GoalSuggestion | null>("/goals/suggestion"),
  setGoalImage: (id: string, file: Blob, name: string) => {
    const form = new FormData();
    form.append("image", file, name);
    return api.form<Goal>("PUT", `/goals/${id}/image`, form);
  },
  removeGoalImage: (id: string) => api.remove<Goal>(`/goals/${id}/image`),
  addReceipts: (expenseId: string, files: File[]) => {
    const form = new FormData();
    for (const f of files) form.append("images", f, f.name);
    return api.form<{ receipt_ids: string[] }>("POST", `/expenses/${expenseId}/receipts`, form);
  },
  removeReceipt: (expenseId: string, fileId: string) => api.delete(`/expenses/${expenseId}/receipts/${fileId}`),
  readReceipt: (file: File) => {
    const form = new FormData();
    form.append("image", file, file.name);
    return api.form<ReceiptReading>("POST", "/receipts/read", form);
  },
  contribute: (id: string, amount: string) =>
    api.post<Goal>(`/goals/${id}/contributions`, { amount }),
  deleteGoal: (id: string) => api.delete(`/goals/${id}`),

  planned: (month?: string) => api.get<Planned[]>(`/planned${month ? `?month=${month}` : ""}`),
  createPlanned: (data: PlannedInput) => api.post<Planned>("/planned", data),
  updatePlanned: (id: string, data: Partial<PlannedInput>) => api.patch<Planned>(`/planned/${id}`, data),
  deletePlanned: (id: string) => api.delete(`/planned/${id}`),
  confirmPlanned: (id: string, paid: boolean) => api.post<Expense>(`/planned/${id}/confirm`, { paid }),
  calendar: (month: string) => api.get<{ month: string; events: CalendarEvent[] }>(`/calendar/${month}`),

  suggestCategory: (description: string) =>
    api.get<CategorySuggestion | null>(`/suggest/category?description=${encodeURIComponent(description)}`),
  suggestDescriptions: (q: string) =>
    api.get<DescriptionSuggestion[]>(`/suggest/descriptions?q=${encodeURIComponent(q)}`),
};

export const keys = {
  month: (month: string) => ["budget", "month", month] as const,
  history: ["budget", "history"] as const,
  categories: ["budget", "categories"] as const,
  recurring: ["budget", "recurring"] as const,
  goals: ["budget", "goals"] as const,
  calendar: (month: string) => ["budget", "calendar", month] as const,
};

export function useMonth(month: string) {
  // Ao trocar de mês, mantém o anterior na tela até o novo chegar (sem "piscar" carregando).
  return useQuery({ queryKey: keys.month(month), queryFn: () => budgetApi.month(month), placeholderData: keepPreviousData });
}

export function useCategories() {
  return useQuery({ queryKey: keys.categories, queryFn: budgetApi.categories, staleTime: 60_000 });
}

/**
 * Mutação que, ao terminar, recarrega os dados do orçamento.
 * Parcelas e fixas afetam outros meses, então todos os meses são recarregados.
 */
export function useBudgetMutation<TArgs, TResult>(fn: (args: TArgs) => Promise<TResult>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["budget"] }),
  });
}
