import { useQuery } from "@tanstack/react-query";

import { api } from "./client";

export type InboxItem = {
  id: string;
  kind: "reply" | "announcement";
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
  created_at: string;
};

export type AnnouncementInput = { title: string; body: string; important: boolean; include_pending: boolean };

export type ResetArea = "entries" | "recurring" | "accounts" | "cards" | "goals" | "investments" | "categories" | "analyses";

export const inboxApi = {
  list: () => api.get<InboxItem[]>("/inbox"),
  unread: () => api.get<{ unread: number }>("/inbox/unread"),
  mark: (id: string, read: boolean) => api.patch<InboxItem>(`/inbox/${id}`, { read }),
  readAll: () => api.post<{ unread: number }>("/inbox/read-all"),

  announcements: () => api.get<Announcement[]>("/admin/announcements"),
  audience: (includePending: boolean) =>
    api.get<{ recipients: number }>(`/admin/announcements/audience?include_pending=${includePending}`),
  announce: (data: AnnouncementInput) => api.post<Announcement>("/admin/announcements", data),

  appearance: (data: { theme?: string; accent?: string }) => api.patch<{ theme: string | null; accent: string | null }>("/me/appearance", data),

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
