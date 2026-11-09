import { useQuery } from "@tanstack/react-query";

import { api } from "./client";

export type InboxItem = {
  id: string;
  kind: "reply" | "announcement" | "alert";
  title: string;
  body: string;
  important: boolean;
  thread_id: string | null;
  read: boolean;
  created_at: string;
};

export type Announcement = {
  id: string;
  title: string;
  body: string;
  important: boolean;
  include_pending: boolean;
  recipients: number;
  read: number;
  replies: number;
  created_at: string;
};

/** v1.3.1: recado com as respostas em thread (pública). */
export type FeedReply = {
  id: string;
  author_name: string;
  avatar_id: string | null;
  from_admin: boolean;
  mine: boolean;
  migrated: boolean;
  can_delete: boolean;
  body: string;
  created_at: string;
};
export type FeedItem = { id: string; title: string; body: string; important: boolean; created_at: string; replies: FeedReply[] };

export const FEED_KEY = ["inbox", "feed"] as const;

export type AnnouncementInput = { title: string; body: string; important: boolean; include_pending: boolean };

export type ResetArea = "entries" | "recurring" | "accounts" | "cards" | "goals" | "investments" | "categories" | "analyses" | "debts";

export const inboxApi = {
  list: () => api.get<InboxItem[]>("/inbox"),
  unread: () => api.get<{ unread: number }>("/inbox/unread"),
  mark: (id: string, read: boolean) => api.patch<InboxItem>(`/inbox/${id}`, { read }),
  readAll: () => api.post<{ unread: number }>("/inbox/read-all"),
  feed: () => api.get<FeedItem[]>("/announcements"),
  reply: (id: string, message: string) => api.post<FeedItem>(`/announcements/${id}/replies`, { message }),
  deleteReply: (id: string) => api.delete(`/announcement-replies/${id}`),

  announcements: () => api.get<Announcement[]>("/admin/announcements"),
  audience: (includePending: boolean) =>
    api.get<{ recipients: number }>(`/admin/announcements/audience?include_pending=${includePending}`),
  announce: (data: AnnouncementInput) => api.post<Announcement>("/admin/announcements", data),

  appearance: (data: { theme?: string; accent?: string; style?: string }) =>
    api.patch<{ theme: string | null; accent: string | null; style: string | null }>("/me/appearance", data),
  financeSettings: (data: { pix_key?: string | null; pix_name?: string | null; pix_city?: string | null; mei?: boolean }) =>
    api.patch<{ pix_key: string | null; pix_name: string | null; pix_city: string | null; mei: boolean }>("/me/finance-settings", data),
  mei: () => api.get<{ year: number; total: string; limit: string; pct: number; count: number }>("/mei"),
  dashboard: (cards: { key: string; visible: boolean }[] | null) => api.put<{ dashboard: string | null }>("/me/dashboard", { cards }),

  resetPreview: () => api.get<{ counts: Record<ResetArea, number> }>("/account/reset"),
  reset: (data: { areas: ResetArea[]; password: string; confirmation: string; code?: string }) =>
    api.post<{ removed: Partial<Record<ResetArea, number>> }>("/account/reset", data),
};

export const INBOX_KEY = ["inbox"] as const;

/** Mensagens não lidas (menu e aba "Mais"); atualiza a cada minuto. */
export function useInboxUnread(enabled = true) {
  return useQuery({
    queryKey: [...INBOX_KEY, "unread"],
    queryFn: inboxApi.unread,
    enabled,
    refetchInterval: 60_000,
    select: (d) => d.unread,
  });
}
