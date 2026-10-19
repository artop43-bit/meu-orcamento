import { useQuery } from "@tanstack/react-query";

import { budgetApi, type Category, type Expense, type Recurring } from "./budget";
import { api } from "./client";
import { parseQuickEntry, type QuickEntry } from "../lib/quickEntry";
import { todayISO } from "../lib/format";

export type Card = {
  id: string;
  name: string;
  limit_amount: string | null;
  closing_day: number;
  due_day: number;
  color: string | null;
  account_id?: string | null;
};

export type CardInput = Omit<Card, "id">;

export type Invoice = {
  month: string;
  closing_date: string;
  due_date: string;
  total: string;
  paid_total: string;
  count: number;
  status: "open" | "closed" | "paid" | "overdue";
};

export type CardSummary = {
  card: Card;
  used: string;
  available: string | null;
  used_pct: number | null;
  best_day: number;
  open_invoice: Invoice;
  closed_invoice: Invoice | null;
};

export type Rule = { id: string; pattern: string; category_id: string };

export type Daily = {
  month: string;
  days: { date: string; balance: string; change: string }[];
  end_balance: string;
  lowest: { date: string; balance: string } | null;
  first_negative: string | null;
  planned_total: string;
  can_spend: { today: string; rest_of_month: string; days_left: number } | null;
};

export type Subscriptions = {
  fixed: { id: string; description: string; amount: string; interval_months: number; category_id: string | null; monthly: string; yearly: string }[];
  candidates: { description: string; amount: string; category_id: string | null; due_day: number | null; months: string[]; yearly: string }[];
  monthly_total: string;
  yearly_total: string;
};

export type FeedbackItem = {
  id: string;
  kind: "bug" | "idea" | "other";
  message: string;
  page: string | null;
  user_agent: string | null;
  app_version: string | null;
  status: "new" | "read" | "done";
  created_at: string;
  email: string | null;
};

export type BulkAction = "pay" | "unpay" | "delete" | "category";

export const extrasApi = {
  cards: () => api.get<CardSummary[]>("/cards"),
  createCard: (data: CardInput) => api.post<Card>("/cards", data),
  updateCard: (id: string, data: Partial<CardInput>) => api.patch<Card>(`/cards/${id}`, data),
  deleteCard: (id: string) => api.delete(`/cards/${id}`),
  invoices: (id: string) => api.get<Invoice[]>(`/cards/${id}/invoices`),
  invoiceItems: (id: string, month: string) => api.get<Expense[]>(`/cards/${id}/invoices/${month}`),
  payInvoice: (id: string, month: string, paid = true) =>
    api.post<{ updated: number }>(`/cards/${id}/invoices/${month}/pay`, { paid }),

  bulk: (ids: string[], action: BulkAction, category_id?: string | null) =>
    api.post<{ count: number }>("/expenses/bulk", { ids, action, category_id: category_id ?? null }),

  rules: () => api.get<Rule[]>("/rules"),
  createRule: (pattern: string, category_id: string) => api.post<Rule>("/rules", { pattern, category_id }),
  deleteRule: (id: string) => api.delete(`/rules/${id}`),

  daily: (month: string) => api.get<Daily>(`/daily?month=${month}`),
  subscriptions: () => api.get<Subscriptions>("/subscriptions"),
  promote: (data: { description: string; amount: string; category_id: string | null; due_day: number | null }) =>
    api.post<Recurring>("/subscriptions/promote", data),

  sendFeedback: (data: { kind: FeedbackItem["kind"]; message: string; page: string; app_version: string }) =>
    api.post<{ status: string }>("/feedback", data),
  feedback: () => api.get<FeedbackItem[]>("/admin/feedback"),
  feedbackStatus: (id: string, status: FeedbackItem["status"]) => api.patch(`/admin/feedback/${id}`, { status }),
};

export const extrasKeys = {
  cards: ["budget", "cards"] as const,
  invoices: (id: string) => ["budget", "cards", id, "invoices"] as const,
  rules: ["budget", "rules"] as const,
  daily: (month: string) => ["budget", "daily", month] as const,
  subscriptions: ["budget", "subscriptions"] as const,
};

export function useCards() {
  return useQuery({ queryKey: extrasKeys.cards, queryFn: extrasApi.cards, staleTime: 30_000 });
}

export function useDaily(month: string) {
  return useQuery({ queryKey: extrasKeys.daily(month), queryFn: () => extrasApi.daily(month) });
}

/**
 * Salva um lançamento escrito numa frase. A categoria vem da sugestão automática
 * (regras, histórico, palavras-chave). Retorna um texto curto do que foi salvo.
 */
export async function saveQuickEntry(
  text: string,
  categories: Category[],
  cards: CardSummary[] = [],
): Promise<{ message: string; revert: () => Promise<unknown> }> {
  const entry: QuickEntry = parseQuickEntry(text);
  if (!entry.amount || entry.description.length < 2) {
    throw new Error("Escreva o que foi e o valor. Ex.: mercado 120 pix ontem");
  }
  const date = entry.date ?? todayISO();
  const month = date.slice(0, 7);
  if (entry.kind === "income") {
    const income = await budgetApi.createIncome(month, {
      description: entry.description,
      amount: entry.amount,
      income_type: "variable",
      day: Number(date.slice(8)),
    });
    return { message: `Renda "${entry.description}" lançada`, revert: () => budgetApi.deleteIncome(income.id) };
  }
  const suggestion = await budgetApi.suggestCategory(entry.description).catch(() => null);
  const category_id = suggestion && categories.some((c) => c.id === suggestion.category_id) ? suggestion.category_id : null;
  // No crédito com um cartão só cadastrado, a compra vai direto para a fatura dele.
  const card = entry.payment === "credit" && cards.length === 1 ? cards[0].card : null;
  const created = await budgetApi.createExpense(month, {
    description: entry.description,
    amount: entry.amount,
    category_id,
    payment_method: entry.payment,
    installments: entry.installments,
    // Na frase, o valor com parcelas é o total da compra ("1800 em 10x" = 10x de 180).
    amount_mode: "total",
    due_date: card ? null : date,
    paid: !entry.installments && !card && date <= todayISO(),
    ...(card ? { card_id: card.id, purchase_date: date } : {}),
  });
  const cat = suggestion?.name ? ` em ${suggestion.name}` : "";
  return {
    message: `"${entry.description}" lançada${cat}${card ? ` na fatura do ${card.name}` : ""}`,
    revert: () => (created.length > 1 ? budgetApi.deleteExpense(created[0].id, "following") : budgetApi.deleteExpense(created[0].id)),
  };
}
