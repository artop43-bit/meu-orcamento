import { useQuery } from "@tanstack/react-query";

import type { Expense } from "./budget";
import { api } from "./client";

export type AccountKind = "checking" | "savings" | "wallet" | "other" | "benefit";

export const ACCOUNT_KINDS: Record<AccountKind, string> = {
  checking: "Conta corrente",
  savings: "Poupança",
  wallet: "Carteira (dinheiro)",
  other: "Outra",
  benefit: "Vale-refeição ou alimentação",
};

export type Account = {
  id: string;
  name: string;
  kind: AccountKind;
  initial_balance: string;
  color: string | null;
  archived: boolean;
  /** v1.4: vale (kind "benefit"): recarga mensal e a categoria que ele paga. */
  benefit_amount?: string | null;
  benefit_day?: number | null;
  benefit_category_id?: string | null;
};

/** v1.4: projeto/etiqueta (despesas de categorias diferentes juntas, com teto opcional). */
export type Project = { id: string; name: string; budget: string | null; total: string; count: number; pct: number | null };
export const PROJECTS_KEY = ["budget", "projects"] as const;

export type AccountBalance = { account: Account; balance: string; end_of_month: string };

export type Transfer = {
  id: string;
  from_account_id: string;
  to_account_id: string;
  amount: string;
  date: string;
  notes: string | null;
};

export type SearchResult = {
  id: string;
  kind: "expense" | "income";
  month: string;
  date: string | null;
  description: string;
  amount: string;
  category_id: string | null;
  payment_method: string | null;
  paid: boolean | null;
};

export type SearchResponse = { results: SearchResult[]; count: number; total_expenses: string; total_incomes: string };

export type PaceRow = {
  category_id: string | null;
  name: string;
  spent: string;
  reference: string;
  reference_kind: "limit" | "average";
  expected_now: string;
  pct: number;
  status: "ok" | "risk" | "over";
};

export type AdminOverview = {
  users: number;
  pending: number;
  blocked: number;
  unverified: number;
  active_7d: number;
  new_7d: number;
  feedback_new: number;
  signup_approval: boolean;
};

export type AdminUser = {
  id: string;
  email: string;
  created_at: string;
  email_verified: boolean;
  access_status: "approved" | "pending" | "blocked";
  approved_at: string | null;
  is_admin: boolean;
  totp_enabled: boolean;
  last_seen_at: string | null;
  active_sessions: number;
  entries: number;
};

export type AdminAction =
  | "approve"
  | "block"
  | "unblock"
  | "revoke_sessions"
  | "verify_email"
  | "resend_verification"
  | "make_admin"
  | "revoke_admin"
  | "delete";

export type SentEmail = { id: string; to: string; subject: string; created_at: string; link: string | null; body: string };

export const moneyApi = {
  accounts: () => api.get<AccountBalance[]>("/accounts"),
  createAccount: (data: Partial<Account> & { name: string }) => api.post<Account>("/accounts", data),
  updateAccount: (id: string, data: Partial<Account>) => api.patch<Account>(`/accounts/${id}`, data),
  deleteAccount: (id: string) => api.delete(`/accounts/${id}`),
  transfers: (month?: string) => api.get<Transfer[]>(`/transfers${month ? `?month=${month}` : ""}`),
  createTransfer: (data: Omit<Transfer, "id">) => api.post<Transfer>("/transfers", data),
  deleteTransfer: (id: string) => api.delete(`/transfers/${id}`),

  review: () => api.get<Expense[]>("/review"),
  confirmReview: (ids: string[], categories?: Record<string, string | null>, category_id?: string | null) =>
    api.post<{ count: number }>("/review/confirm", { ids, categories, category_id: category_id ?? null }),

  projects: () => api.get<Project[]>("/projects"),
  updateProject: (id: string, data: { name?: string; budget?: string | null }) => api.patch<{ id: string; name: string }>(`/projects/${id}`, data),
  deleteProject: (id: string) => api.delete(`/projects/${id}`),
  search: (params: Record<string, string>) => {
    const query = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== "")).toString();
    return api.get<SearchResponse>(`/search${query ? `?${query}` : ""}`);
  },
  pace: (month: string) => api.get<PaceRow[]>(`/analysis/pace?month=${month}`),
  copyCandidates: (month: string) => api.get<Expense[]>(`/months/${month}/copy-candidates`),
  copyPrevious: (month: string, ids: string[]) => api.post<Expense[]>(`/months/${month}/copy-previous`, { ids }),

  adminOverview: () => api.get<AdminOverview>("/admin/overview"),
  adminUsers: () => api.get<AdminUser[]>("/admin/users"),
  adminAction: (id: string, action: AdminAction) => api.post<{ status: string }>(`/admin/users/${id}/action`, { action }),
  adminEmails: () => api.get<SentEmail[]>("/admin/emails"),
};

export const moneyKeys = {
  accounts: ["budget", "accounts"] as const,
  review: ["budget", "review"] as const,
};

export function useAccounts() {
  return useQuery({ queryKey: moneyKeys.accounts, queryFn: moneyApi.accounts, staleTime: 30_000 });
}

export function useReviewCount() {
  const q = useQuery({ queryKey: moneyKeys.review, queryFn: moneyApi.review, staleTime: 60_000 });
  return q.data?.length ?? 0;
}
