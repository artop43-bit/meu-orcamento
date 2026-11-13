import { api } from "./client";

export type MonthAlert = {
  kind: "unusual" | "new_merchant" | "price_up" | "renewal" | "loan_late";
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

export type LoanMode = "none" | "total" | "simple" | "price" | "sac";
export type LoanFrequency = "day" | "week" | "biweek" | "month";
export type LoanTarget = "rate" | "profit" | "installment" | "total";
export type Direction = "owes_me" | "i_owe";

export type LoanInstallment = {
  number: number;
  due_date: string;
  amount: string;
  interest: string;
  principal: string;
  received_amount: string | null;
  received_at: string | null;
  open: string;
  status: "paid" | "partial" | "late" | "open";
  late_charge: string;
};

export type FriendLoan = {
  id: string;
  person: string;
  description: string | null;
  direction: Direction;
  principal: string;
  mode: LoanMode;
  rate: string;
  frequency: LoanFrequency;
  count: number;
  first_due: string;
  late_fee: string | null;
  late_interest: string | null;
  created_at: string;
  settled_at: string | null;
  total: string;
  received: string;
  remaining: string;
  profit: string;
  profit_received: string;
  paid_count: number;
  late_count: number;
  late_amount: string;
  next: LoanInstallment | null;
  monthly_equivalent: number;
  yearly_equivalent: number;
  payback: number | null;
  installments: LoanInstallment[];
};

export type LoanTotals = {
  lent: string;
  lent_count: number;
  to_receive: string;
  profit_expected: string;
  profit_received: string;
  yearly: number | null;
  late_count: number;
};

export type SimulateInput = {
  principal: string;
  mode: LoanMode;
  target: LoanTarget;
  rate?: string;
  value?: string;
  frequency: LoanFrequency;
  count: number;
  first_due: string;
  market?: boolean;
};

export type Simulation = {
  mode: LoanMode;
  rate: number;
  frequency: LoanFrequency;
  count: number;
  principal: string;
  total: string;
  profit: string;
  installment: string;
  last_installment: string;
  equal_installments: boolean;
  monthly_equivalent: number;
  yearly_equivalent: number;
  usury_warning: boolean;
  payback: number | null;
  stop_at: number;
  loss_if_stops: string;
  schedule: { number: number; due_date: string; amount: string; interest: string; principal: string; balance: string }[];
  compare: { mode: LoanMode; label: string; rate: number; first: string; last: string }[];
  market: { cdi_year: number | null; cdb_net: string | null; ipca_year: number | null; real_profit: string | null } | null;
};

export type LoanInput = SimulateInput & {
  person: string;
  description: string;
  direction: Direction;
  late_fee?: string | null;
  late_interest?: string | null;
};

export type SplitPersonRow = { person: string; balance: string; items: Share[]; loans: FriendLoan[] };

export type SplitBoard = {
  people: SplitPersonRow[];
  owed_to_me: string;
  i_owe: string;
  names: string[];
  history: Share[];
  loans: LoanTotals;
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
  simulate: (data: SimulateInput) => api.post<Simulation>("/friend-loans/simulate", data),
  createLoan: (data: LoanInput) => api.post<FriendLoan>("/friend-loans", data),
  removeLoan: (id: string) => api.delete(`/friend-loans/${id}`),
  receive: (id: string, data: { number: number; amount?: string; on?: string }) => api.post<FriendLoan>(`/friend-loans/${id}/receive`, data),
  undoReceive: (id: string, number: number) => api.remove<FriendLoan>(`/friend-loans/${id}/receive/${number}`),
  payoffQuote: (id: string, discount: boolean) =>
    api.get<{ remaining: string; discount: string; value: string }>(`/friend-loans/${id}/payoff?discount=${discount}`),
  payoff: (id: string, discount: boolean) => api.post<FriendLoan>(`/friend-loans/${id}/payoff`, { discount }),
  cycle: (month_start_day: number) => api.patch<{ month_start_day: number }>("/me/cycle", { month_start_day }),
};
