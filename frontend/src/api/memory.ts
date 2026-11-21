import { useQuery } from "@tanstack/react-query";

import { api } from "./client";

export type VaultCategory =
  | "warranty"
  | "contract"
  | "fiscal"
  | "receipt"
  | "certificate"
  | "identity"
  | "other";

export type VaultExpiryStatus = "valid" | "expiring_soon" | "expired" | "no_expiry";

export interface VaultDocument {
  id: string;
  title: string;
  category: VaultCategory;
  category_label: string;
  issuer: string | null;
  document_number: string | null;
  issue_date: string | null;
  expires_at: string | null;
  notify_days_before: number;
  expiry_status: VaultExpiryStatus;
  days_left: number | null;
  notes: string | null;
  file_name: string;
  mime_type: string;
  size_bytes: number;
  ocr_used: boolean;
  has_extracted_text: boolean;
  extracted_preview: string | null;
  file_url: string;
  contact_id: string | null;
  deal_id: string | null;
  project_id: string | null;
  proposal_id: string | null;
  messaging_media_id: string | null;
  warning?: string | null;
  created_at: string;
  updated_at: string;
}

export interface VaultSummary {
  total_docs: number;
  valid_count: number;
  expiring_count: number;
  expired_count: number;
  no_expiry_count: number;
  ocr_indexed_count: number;
  vault_bytes: number;
  account_used_bytes: number;
  quota_mb: number;
}

export interface VaultListResponse {
  documents: VaultDocument[];
  summary: VaultSummary;
}

export interface VaultBridges {
  contacts: { id: string; name: string }[];
  deals: { id: string; title: string; status: string }[];
  projects: { id: string; name: string; status: string }[];
  proposals: { id: string; title: string; number: number }[];
}

export type NoteTemplateKind = "blank" | "meeting" | "sales_script" | "sop" | "planning";

export interface NoteTemplateOption {
  id: NoteTemplateKind;
  label: string;
  folder: string;
  title: string;
  content: string;
}

export interface NotebookLinkRef {
  label: string;
  target_id: string | null;
  target_title: string | null;
}

export interface NotebookNote {
  id: string;
  title: string;
  folder: string;
  tags: string[];
  pinned: boolean;
  template_kind: NoteTemplateKind;
  content: string;
  links: NotebookLinkRef[];
  backlinks: { id: string; title: string }[];
  score: number | null;
  contact_id: string | null;
  deal_id: string | null;
  project_id: string | null;
  messaging_chat_id: string | null;
  goal_id: string | null;
  vault_doc_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface NotebookListResponse {
  notes: NotebookNote[];
  summary: {
    total_notes: number;
    pinned_count: number;
    folders: string[];
    total_links: number;
  };
}

export interface NotebookBridges extends Omit<VaultBridges, "proposals"> {
  chats: { id: string; name: string }[];
  goals: { id: string; name: string }[];
  vault_docs: { id: string; title: string; category: string }[];
}

export const vaultApi = {
  list: (params: { category?: string; expiry_status?: string; q?: string } = {}) => {
    const qs = new URLSearchParams();
    if (params.category && params.category !== "all") qs.set("category", params.category);
    if (params.expiry_status && params.expiry_status !== "all") {
      qs.set("expiry_status", params.expiry_status);
    }
    if (params.q?.trim()) qs.set("q", params.q.trim());
    const suffix = qs.toString() ? `?${qs}` : "";
    return api.get<VaultListResponse>(`/cofre/documents${suffix}`);
  },
  bridges: () => api.get<VaultBridges>("/cofre/hub/bridges"),
  upload: (form: FormData) => api.form<VaultDocument>("POST", "/cofre/documents", form),
  update: (id: string, body: Partial<VaultDocument>) =>
    api.patch<VaultDocument>(`/cofre/documents/${id}`, body),
  delete: (id: string) => api.delete(`/cofre/documents/${id}`),
  archiveFromMessaging: (
    mediaId: string,
    body: { title?: string; category?: VaultCategory; expires_at?: string | null } = {},
  ) =>
    api.post<{ archived: boolean; document: VaultDocument }>(
      `/cofre/from-messaging/${mediaId}`,
      body,
    ),
  archiveFromProposal: (
    docId: string,
    body: { category?: VaultCategory; expires_at?: string | null } = {},
  ) =>
    api.post<{ archived: boolean; document: VaultDocument }>(
      `/cofre/from-proposal/${docId}`,
      body,
    ),
};

export const notebookApi = {
  templates: () => api.get<NoteTemplateOption[]>("/caderno/templates"),
  bridges: () => api.get<NotebookBridges>("/caderno/hub/bridges"),
  list: (params: { q?: string; folder?: string; pinned_only?: boolean } = {}) => {
    const qs = new URLSearchParams();
    if (params.q?.trim()) qs.set("q", params.q.trim());
    if (params.folder && params.folder !== "all") qs.set("folder", params.folder);
    if (params.pinned_only) qs.set("pinned_only", "true");
    const suffix = qs.toString() ? `?${qs}` : "";
    return api.get<NotebookListResponse>(`/caderno/notes${suffix}`);
  },
  create: (body: {
    title?: string;
    folder?: string;
    tags?: string[];
    pinned?: boolean;
    template_kind?: NoteTemplateKind;
    content?: string;
    contact_id?: string | null;
    deal_id?: string | null;
    project_id?: string | null;
    messaging_chat_id?: string | null;
    goal_id?: string | null;
    vault_doc_id?: string | null;
  }) => api.post<NotebookNote>("/caderno/notes", body),
  update: (id: string, body: Partial<NotebookNote>) =>
    api.patch<NotebookNote>(`/caderno/notes/${id}`, body),
  delete: (id: string) => api.delete(`/caderno/notes/${id}`),
};

export function useVaultDocuments(q: string = "", category: string = "all", expiry: string = "all") {
  return useQuery({
    queryKey: ["cofre", "documents", q, category, expiry],
    queryFn: () => vaultApi.list({ q, category, expiry_status: expiry }),
  });
}

export function useVaultBridges(enabled: boolean) {
  return useQuery({
    queryKey: ["cofre", "bridges"],
    queryFn: vaultApi.bridges,
    enabled,
  });
}

export function useNotebookNotes(q: string = "", folder: string = "all", pinnedOnly: boolean = false) {
  return useQuery({
    queryKey: ["caderno", "notes", q, folder, pinnedOnly],
    queryFn: () => notebookApi.list({ q, folder, pinned_only: pinnedOnly }),
  });
}

export function useNotebookTemplates() {
  return useQuery({
    queryKey: ["caderno", "templates"],
    queryFn: notebookApi.templates,
    staleTime: Infinity,
  });
}

export function useNotebookBridges(enabled: boolean) {
  return useQuery({
    queryKey: ["caderno", "bridges"],
    queryFn: notebookApi.bridges,
    enabled,
  });
}
