import { api } from "./client";

/** v1.3: desafios de economia e o plano "sem culpa" para o mês no negativo. */

export type ChallengeKind = "no_keyword" | "no_category" | "no_nonessential" | "max_category";

export type ChallengeTemplate = { key: string; title: string; kind: ChallengeKind; days: number; text: string; category: string | null };

export type Challenge = {
  id: string;
  title: string;
  kind: ChallengeKind;
  category_id: string | null;
  keywords: string | null;
  max_amount: string | null;
  start_date: string;
  end_date: string;
  days: number;
  elapsed_days: number;
  status: "active" | "won" | "lost";
  spent: string;
  slips: { description: string; amount: string; date: string }[];
};

export type ChallengeInput = {
  template?: string;
  title?: string;
  kind?: ChallengeKind;
  category_id?: string | null;
  keywords?: string | null;
  max_amount?: string | null;
  days?: number;
};

export type Recovery = {
  month: string;
  deficit: string;
  spread: { months: number; per_month: string }[];
  cuts: { category_id: string | null; name: string; total: string; average: string; above_average: string }[];
  fixed: { description: string; monthly: string }[];
};

export const CHALLENGES_KEY = ["budget", "challenges"] as const;

export const habitsApi = {
  templates: () => api.get<ChallengeTemplate[]>("/challenges/templates"),
  challenges: () => api.get<Challenge[]>("/challenges"),
  createChallenge: (data: ChallengeInput) => api.post<Challenge>("/challenges", data),
  deleteChallenge: (id: string) => api.delete(`/challenges/${id}`),
  recovery: (month: string) => api.get<Recovery>(`/months/${month}/recovery`),
};
