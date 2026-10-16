import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";

export type Category = { id: string; name: string; is_essential: boolean; color: string | null };

export type Income = {
  id: string;
  month: string;
  description: string;
  amount: string;
  recurring_id: string | null;
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
  installment_group_id: string | null;
  installment_number: number | null;
  installment_total: number | null;
  recurring_id: string | null;
};

export type CategoryTotal = {
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
};

export type Goal = {
  id: string;
  name: string;
  target_amount: string;
  current_amount: string;
  target_date: string | null;
  progress_pct: number;
};

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

export type ExpenseInput = {
  description: string;
  amount: string;
  category_id?: string | null;
  due_date?: string | null;
  notes?: string | null;
  installments?: number | null;
};

export type RecurringInput = {
  kind: "income" | "expense";
  description: string;
  amount: string;
  category_id?: string | null;
  due_day?: number | null;
  start_month: string;
  end_month?: string | null;
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

  createIncome: (month: string, data: { description: string; amount: string }) =>
    api.post<Income>(`/months/${month}/incomes`, data),
  updateIncome: (id: string, data: Partial<{ description: string; amount: string }>) =>
    api.patch<Income>(`/incomes/${id}`, data),
  deleteIncome: (id: string, scope: DeleteScope = "one") =>
    api.delete(`/incomes/${id}?scope=${scope}`),

  createExpense: (month: string, data: ExpenseInput) =>
    api.post<Expense[]>(`/months/${month}/expenses`, data),
  updateExpense: (id: string, data: Partial<ExpenseInput & { paid: boolean }>) =>
    api.patch<Expense>(`/expenses/${id}`, data),
  deleteExpense: (id: string, scope: DeleteScope = "one") =>
    api.delete(`/expenses/${id}?scope=${scope}`),

  recurring: () => api.get<Recurring[]>("/recurring"),
  createRecurring: (data: RecurringInput) => api.post<Recurring>("/recurring", data),
  updateRecurring: (id: string, data: Partial<Omit<RecurringInput, "kind" | "start_month">>) =>
    api.patch<Recurring>(`/recurring/${id}`, data),
  deleteRecurring: (id: string) => api.delete(`/recurring/${id}`),

  goals: () => api.get<Goal[]>("/goals"),
  createGoal: (data: { name: string; target_amount: string; target_date?: string | null }) =>
    api.post<Goal>("/goals", data),
  updateGoal: (id: string, data: Partial<{ name: string; target_amount: string; target_date: string | null }>) =>
    api.patch<Goal>(`/goals/${id}`, data),
  contribute: (id: string, amount: string) =>
    api.post<Goal>(`/goals/${id}/contributions`, { amount }),
  deleteGoal: (id: string) => api.delete(`/goals/${id}`),
};

export const keys = {
  month: (month: string) => ["budget", "month", month] as const,
  history: ["budget", "history"] as const,
  categories: ["budget", "categories"] as const,
  recurring: ["budget", "recurring"] as const,
  goals: ["budget", "goals"] as const,
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
