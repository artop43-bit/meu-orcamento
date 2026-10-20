import { api } from "./client";

export type LoanKind = "home" | "vehicle" | "personal" | "payroll" | "overdraft" | "other";

export type LoanInput = {
  kind: LoanKind;
  name: string;
  institution: string | null;
  principal: string;
  rate: string;
  rate_period: "monthly" | "yearly";
  system: "price" | "sac";
  installments: number;
  first_due: string;
  paid_before: number;
  insurance_monthly: string;
  fee_monthly: string;
  iof: string;
  category_id: string | null;
  account_id: string | null;
  notes: string | null;
};

export type Loan = LoanInput & {
  id: string;
  kind_label: string;
  monthly_rate: number;
  yearly_rate: number;
  cet_monthly: number;
  cet_yearly: number;
  first_payment: string;
  last_payment: string;
  total_paid: string;
  total_interest: string;
  paid_installments: number;
  balance: string;
  next_payment: string | null;
  next_due: string | null;
  end: string;
};

export type Installment = {
  number: number;
  due: string;
  payment: string;
  interest: string;
  amortization: string;
  extras: string;
  balance: string;
};

export type ExtraResult = {
  after: number;
  balance_before: string;
  amount: string;
  mode: "term" | "payment";
  months_before: number;
  months_after: number;
  payment_before: string;
  payment_after: string;
  interest_before: string;
  interest_after: string;
  interest_saved: string;
  end_after: string | null;
};

export type OtherDebt = { id: string; name: string; balance: string; monthly_payment: string | null; notes: string | null };
export type OtherDebtInput = Omit<OtherDebt, "id">;

export type DebtsOverview = {
  loans: Loan[];
  others: OtherDebt[];
  card_installments: string;
  debts: string;
  monthly_payments: string;
  assets: string;
  investments: string;
  accounts: string;
  net_worth: string;
  history: { month: string; assets: string; debts: string; net: string }[];
};

export const DEBTS_KEY = ["debts"] as const;

export const LOAN_KINDS: [LoanKind, string][] = [
  ["home", "Financiamento imobiliário"],
  ["vehicle", "Financiamento de veículo"],
  ["personal", "Empréstimo pessoal"],
  ["payroll", "Empréstimo consignado"],
  ["overdraft", "Cheque especial"],
  ["other", "Outro"],
];

export const debtsApi = {
  overview: () => api.get<DebtsOverview>("/debts"),
  createLoan: (data: LoanInput) => api.post<Loan>("/loans", data),
  updateLoan: (id: string, data: Partial<LoanInput>) => api.patch<Loan>(`/loans/${id}`, data),
  deleteLoan: (id: string) => api.delete(`/loans/${id}`),
  table: (id: string) => api.get<Installment[]>(`/loans/${id}/table`),
  simulate: (id: string, data: { amount: string; after?: number; mode: "term" | "payment" }) =>
    api.post<ExtraResult>(`/loans/${id}/simulate`, data),
  createOther: (data: OtherDebtInput) => api.post<OtherDebt>("/other-debts", data),
  updateOther: (id: string, data: OtherDebtInput) => api.put<OtherDebt>(`/other-debts/${id}`, data),
  deleteOther: (id: string) => api.delete(`/other-debts/${id}`),
};
