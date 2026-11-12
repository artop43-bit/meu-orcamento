import { api, ApiError } from "./client";

export type LegacyIncome = { description: string; amount: string; recurring: boolean };
export type LegacyExpense = {
  description: string;
  amount: string;
  category_name: string | null;
  due_day: number | null;
  paid: boolean;
  notes: string | null;
  installment_current: number | null;
  installment_total: number | null;
  recurring: boolean;
};
export type LegacyGoal = { name: string; target_amount: string; current_amount: string };
export type LegacyHistory = { month: string; income: string; expenses: string };

export type LegacyImport = {
  month: string;
  incomes: LegacyIncome[];
  expenses: LegacyExpense[];
  goals: LegacyGoal[];
  history: LegacyHistory[];
  reserve: string | null;
};
export type LegacyPreview = LegacyImport & { already_imported: boolean };
export type LegacyResult = {
  incomes: number;
  expenses: number;
  goals: number;
  history_months: number;
  investments: number;
};

export type StatementTransaction = {
  ref: string;
  date: string;
  description: string;
  amount: string;
  kind: "income" | "expense";
  category_id: string | null;
  /** v1.4: lançamento feito à mão que esta linha confere (não entra de novo). */
  match_id?: string | null;
};
export type StatementMatch = { id: string; kind: "income" | "expense"; description: string; date: string };
export type StatementPreview = {
  format: "ofx" | "csv" | "xlsx";
  transactions: (StatementTransaction & { duplicate: boolean; card_payment?: boolean; match?: StatementMatch | null })[];
  period?: { start: string; end: string } | null;
};

/** Campos do arquivo: índice da coluna de cada um (null = não existe). */
export type ColumnMapping = {
  header_row: number;
  date: number | null;
  description: number | null;
  amount: number | null;
  credit: number | null;
  debit: number | null;
};

export type ImportAnalysis = {
  format: "ofx" | "csv" | "xlsx" | "backup" | "legacy";
  kind: "account" | "card" | "backup" | "legacy";
  invert?: boolean;
  count?: number;
  columns?: string[];
  sample?: string[][];
  mapping?: ColumnMapping;
  mapping_source?: "auto" | "saved";
  signature?: string | null;
  ready?: boolean;
  summary?: Record<string, number>;
};

export type ImportBatch = {
  id: string;
  filename: string;
  file_format: string;
  count: number;
  created_at: string;
  undone_at: string | null;
};

export type ExportFilters = {
  start: string;
  end: string;
  kind: "all" | "expense" | "income";
  categories: string[];
  places: { accounts: string[]; cards: string[] };
};

export type AnnualSummary = {
  year: number;
  income: string;
  expenses: string;
  balance: string;
  savings_rate: number | null;
  months: { month: string; income: string; expenses: string; balance: string; committed_pct: number | null }[];
  by_category: { name: string; total: string; share: number }[];
  investments_total: string;
  goals: { name: string; target_amount: string; current_amount: string; completed: boolean }[];
  /** v1.4: relatório para o Imposto de Renda. */
  tax?: TaxReport;
};

export type TaxReport = {
  year: number;
  deductions: { kind: string; label: string; total: string; items: { date: string; description: string; category: string; amount: string }[] }[];
  deductions_total: string;
  incomes: { kind: string; label: string; total: string }[];
  assets: { description: string; value: string }[];
  debts: { description: string; value: string }[];
};

function fileForm(file: File, extra: Record<string, string> = {}): FormData {
  const form = new FormData();
  form.append("file", file, file.name);
  for (const [key, value] of Object.entries(extra)) form.append(key, value);
  return form;
}

export function exportQuery(f: ExportFilters): string {
  const q = new URLSearchParams({ start: f.start, end: f.end, kind: f.kind });
  for (const id of f.categories) q.append("category", id);
  for (const id of f.places.accounts) q.append("account", id);
  for (const id of f.places.cards) q.append("card", id);
  return q.toString();
}

export const dataApi = {
  legacyPreview: (month: string, data: unknown) =>
    api.post<LegacyPreview>("/import/legacy/preview", { month, data }),
  legacyImport: (payload: LegacyImport) => api.post<LegacyResult>("/import/legacy", payload),
  statementPreview: (filename: string, content: string, invert: boolean) =>
    api.post<StatementPreview>("/import/statement/preview", { filename, content, invert }),
  statementImport: (transactions: StatementTransaction[]) =>
    api.post<{ created: number; skipped: number }>("/import/statement", { transactions }),

  analyze: (file: File) => api.form<ImportAnalysis>("POST", "/import/analyze", fileForm(file)),
  preview: (file: File, mapping: ColumnMapping | undefined, invert: boolean) =>
    api.form<StatementPreview>(
      "POST",
      "/import/preview",
      fileForm(file, { ...(mapping ? { mapping: JSON.stringify(mapping) } : {}), invert: String(invert) }),
    ),
  commit: (payload: {
    transactions: StatementTransaction[];
    filename: string;
    file_format: "ofx" | "csv" | "xlsx";
    account_id?: string | null;
    card_id?: string | null;
    save_mapping?: { signature: string; mapping: ColumnMapping } | null;
  }) => api.post<{ batch_id: string; created: number; skipped: number; matched?: number }>("/import/commit", payload),
  restore: (file: File) => api.form<Record<string, number>>("POST", "/import/restore", fileForm(file)),
  batches: () => api.get<ImportBatch[]>("/import/batches"),
  undo: (id: string) => api.post<{ removed: number }>(`/import/batches/${id}/undo`),
  exportCount: (f: ExportFilters) =>
    api.get<{ count: number; income: string; expenses: string; balance: string }>(`/export/count?${exportQuery(f)}`),
  annual: (year: number) => api.get<AnnualSummary>(`/export/annual?year=${year}`),
};

/** Lê um arquivo como texto: UTF-8, ou Windows-1252 (comum em extratos de bancos brasileiros). */
export async function readTextFile(file: File): Promise<string> {
  const buffer = await file.arrayBuffer();
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(buffer).replace(/^﻿/, "");
  } catch {
    return new TextDecoder("windows-1252").decode(buffer);
  }
}

/** Baixa um arquivo da API (usa o cookie de sessão) e salva com o nome sugerido pelo servidor. */
export async function download(path: string, fallbackName: string): Promise<void> {
  const response = await fetch(`/api${path}`, { credentials: "include" });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new ApiError(response.status, data?.error ?? "error", data?.message ?? "Não foi possível exportar.");
  }
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const name = /filename="([^"]+)"/.exec(disposition)?.[1] ?? fallbackName;
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
