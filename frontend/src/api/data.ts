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
};
export type StatementPreview = {
  format: "ofx" | "csv";
  transactions: (StatementTransaction & { duplicate: boolean })[];
};

export const dataApi = {
  legacyPreview: (month: string, data: unknown) =>
    api.post<LegacyPreview>("/import/legacy/preview", { month, data }),
  legacyImport: (payload: LegacyImport) => api.post<LegacyResult>("/import/legacy", payload),
  statementPreview: (filename: string, content: string, invert: boolean) =>
    api.post<StatementPreview>("/import/statement/preview", { filename, content, invert }),
  statementImport: (transactions: StatementTransaction[]) =>
    api.post<{ created: number; skipped: number }>("/import/statement", { transactions }),
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
