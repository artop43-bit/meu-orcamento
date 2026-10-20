import { api } from "./client";

export type MonthAlert = {
  kind: "unusual" | "new_merchant" | "price_up" | "renewal";
  key: string;
  title: string;
  text: string;
  expense_id: string | null;
};

export type Share = {
  id: string;
  expense_id: string | null;
  person: string;
  description: string;
  amount: string;
  direction: "owes_me" | "i_owe";
  created_at: string;
  settled_at: string | null;
};

export type SplitBoard = {
  people: { person: string; balance: string; items: Share[] }[];
  owed_to_me: string;
  i_owe: string;
  names: string[];
  history: Share[];
};

export type SplitMode = "equal" | "amount" | "percent";

export const SPLITS_KEY = ["splits"] as const;

export const sharingApi = {
  alerts: (month: string) => api.get<MonthAlert[]>(`/alerts?month=${month}`),
  board: () => api.get<SplitBoard>("/splits"),
  expenseSplit: (expenseId: string) => api.get<Share[]>(`/expenses/${expenseId}/split`),
  split: (expenseId: string, data: { people: { person: string; value?: string }[]; mode: SplitMode; include_me: boolean }) =>
    api.put<Share[]>(`/expenses/${expenseId}/split`, data),
  addManual: (data: { person: string; description: string; amount: string; direction: "owes_me" | "i_owe" }) => api.post<Share>("/splits", data),
  remove: (id: string) => api.delete(`/splits/${id}`),
  settle: (person: string, record_income: boolean) =>
    api.post<{ person: string; balance: string; income_id: string | null }>("/splits/settle", { person, record_income }),
  cycle: (month_start_day: number) => api.patch<{ month_start_day: number }>("/me/cycle", { month_start_day }),
};
