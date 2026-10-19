import { useQuery } from "@tanstack/react-query";

import { api } from "./client";

export type StatKey =
  | "avg_income"
  | "avg_expenses"
  | "savings_rate"
  | "goals_completed"
  | "positive_months"
  | "best_streak"
  | "score";

export type ProfilePrefs = { stats: Record<StatKey, boolean>; show_values_in_recap: boolean };

export type Profile = {
  display_name: string | null;
  bio: string | null;
  city: string | null;
  profession: string | null;
  email: string;
  member_since: string;
  avatar_id: string | null;
  banner_id: string | null;
  prefs: ProfilePrefs;
};

export type ProfileSummary = {
  months: number;
  avg_income: string | null;
  avg_expenses: string | null;
  savings_rate: number | null;
  goals_completed: number;
  goals_total: number;
  positive_months: number;
  best_streak: number;
  score: number | null;
  score_label: string | null;
};

export type Retrospective = {
  period: "month" | "year";
  start: string;
  end: string;
  has_data: boolean;
  income: string;
  expenses: string;
  balance: string;
  savings_rate: number | null;
  expenses_change_pct: number | null;
  top_category: { name: string; total: string; share_pct: number | null } | null;
  most_saved_category: { name: string; saved: string } | null;
  best_month: { month: string; balance: string } | null;
  positive_months: number;
  months_with_data: number;
  entries: number;
  goals_completed: number;
  show_values: boolean;
};

export type ProfilePatch = Partial<Pick<Profile, "display_name" | "bio" | "city" | "profession">> & {
  prefs?: { stats?: Partial<Record<StatKey, boolean>>; show_values_in_recap?: boolean };
};

export const profileApi = {
  get: () => api.get<Profile>("/profile"),
  update: (data: ProfilePatch) => api.patch<Profile>("/profile", data),
  setImage: (purpose: "avatar" | "banner", file: Blob, name: string) => {
    const form = new FormData();
    form.append("image", file, name);
    return api.form<Profile>("PUT", `/profile/${purpose}`, form);
  },
  removeImage: (purpose: "avatar" | "banner") => api.remove<Profile>(`/profile/${purpose}`),
  summary: () => api.get<ProfileSummary>("/profile/summary"),
  retrospective: (period: "month" | "year", value: string) =>
    api.get<Retrospective>(
      period === "month" ? `/profile/retrospective?period=month&month=${value}` : `/profile/retrospective?period=year&year=${value}`,
    ),
};

export function useProfile() {
  return useQuery({ queryKey: ["profile"], queryFn: profileApi.get, staleTime: 60_000 });
}
