import { useQuery } from "@tanstack/react-query";

import { api } from "./client";

export type ColumnType = "text" | "number" | "currency" | "date" | "phone" | "email" | "boolean";
export type WidgetType = "kpi" | "bar" | "line" | "donut" | "funnel" | "table";
export type DateRangeKey = "all" | "7d" | "30d" | "90d" | "month" | "year";
export type DashboardTemplate =
  | "blank"
  | "crm_overview"
  | "messaging_overview"
  | "budget_overview"
  | "dataset";

export interface ColumnDef {
  name: string;
  label: string;
  type: ColumnType;
}

export interface HubMessagingChatOption {
  id: string;
  name: string;
  phone: string | null;
  phone_display: string;
  budget_person: string | null;
}

export interface CrmContact {
  id: string;
  name: string;
  phone: string | null;
  phone_display: string | null;
  remote_jid: string | null;
  email: string | null;
  company: string | null;
  origin: string | null;
  tags: string[];
  notes: string | null;
  messaging_chat_id: string | null;
  budget_person: string | null;
  created_at: string;
  updated_at: string;
}

export interface CrmDeal {
  id: string;
  pipeline_id: string;
  stage_id: string;
  contact_id: string | null;
  contact_name: string | null;
  contact_phone: string | null;
  contact_messaging_chat_id: string | null;
  title: string;
  value: string;
  status: "open" | "won" | "lost";
  expected_close_date: string | null;
  budget_income_id: string | null;
  notes: string | null;
  position: number;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CrmStageBoard {
  id: string;
  name: string;
  position: number;
  is_won: boolean;
  is_lost: boolean;
  total_value: string;
  deals: CrmDeal[];
}

export interface PipelineBoard {
  pipeline: { id: string; name: string };
  stages: CrmStageBoard[];
  summary: {
    total_deals: number;
    open_value: string;
    won_value: string;
  };
}

export interface CrmActivity {
  id: string;
  contact_id: string | null;
  deal_id: string | null;
  kind: "note" | "task" | "call" | "message" | "budget";
  body: string;
  due_at: string | null;
  done_at: string | null;
  created_at: string;
}

export interface DataSourceItem {
  id: string;
  name: string;
  kind:
    | "native_crm"
    | "native_crm_contacts"
    | "native_messaging"
    | "native_budget"
    | "pdf"
    | "csv"
    | "api";
  description: string | null;
  config: Record<string, unknown>;
  has_credentials: boolean;
  schema: ColumnDef[];
  row_count: number;
  last_synced_at: string | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface PreviewSuggestions {
  recommended_target: "dataset" | "contacts" | "deals";
  contact_mapping: Record<string, string>;
  deal_mapping: Record<string, string>;
}

export interface PdfPreviewResponse {
  filename: string;
  strategy: string;
  used_ocr: boolean;
  pages: number;
  ocr_pages: number;
  warning?: string | null;
  raw_text_excerpt: string;
  columns: ColumnDef[];
  rows: Record<string, unknown>[];
  total_rows: number;
  suggestions: PreviewSuggestions;
}

export interface CsvPreviewResponse {
  filename: string;
  delimiter: string;
  columns: ColumnDef[];
  rows: Record<string, unknown>[];
  total_rows: number;
  suggestions: PreviewSuggestions;
}

export interface ApiPreviewResponse {
  columns: ColumnDef[];
  rows: Record<string, unknown>[];
  total_rows: number;
  suggestions: PreviewSuggestions;
}

export interface DashboardSummary {
  id: string;
  name: string;
  description: string | null;
  is_default: boolean;
  default_range: DateRangeKey;
  widgets_count: number;
  created_at: string;
  updated_at: string;
}

export interface WidgetSeriesItem {
  label: string;
  value: number;
  count: number;
}

export interface WidgetResult {
  widget_type: WidgetType;
  value?: number;
  format?: "currency" | "number";
  count?: number;
  total?: number;
  series?: WidgetSeriesItem[];
  columns?: ColumnDef[];
  rows?: Record<string, unknown>[];
  total_rows?: number;
}

export interface DashboardWidget {
  id: string;
  dashboard_id: string;
  source_id: string | null;
  source_name: string | null;
  title: string;
  widget_type: WidgetType;
  span: 1 | 2;
  position: number;
  query: Record<string, unknown>;
  result: WidgetResult;
}

export interface DashboardView {
  id: string;
  name: string;
  description: string | null;
  is_default: boolean;
  default_range: DateRangeKey;
  active_range: DateRangeKey;
  widgets: DashboardWidget[];
}

export const crmKeys = {
  pipeline: ["crm", "pipeline"] as const,
  contacts: (q = "") => ["crm", "contacts", q] as const,
  messagingChats: ["crm", "hub", "messaging-chats"] as const,
  activities: (dealId?: string | null, contactId?: string | null) =>
    ["crm", "activities", dealId ?? "", contactId ?? ""] as const,
  sources: ["crm", "sources"] as const,
  sourceRows: (id: string) => ["crm", "source-rows", id] as const,
  dashboards: ["crm", "dashboards"] as const,
  dashboard: (id: string, range: DateRangeKey) => ["crm", "dashboard", id, range] as const,
};

export const crmApi = {
  pipeline: () => api.get<PipelineBoard>("/crm/pipeline"),
  messagingChats: () => api.get<HubMessagingChatOption[]>("/crm/hub/messaging-chats"),
  contacts: (q = "") =>
    api.get<CrmContact[]>(`/crm/contacts${q.trim() ? `?q=${encodeURIComponent(q.trim())}` : ""}`),
  createContact: (body: {
    name: string;
    phone?: string;
    email?: string;
    company?: string;
    origin?: string;
    tags?: string[];
    notes?: string;
    messaging_chat_id?: string | null;
    budget_person?: string;
  }) => api.post<CrmContact>("/crm/contacts", body),
  importFromMessaging: (chatId: string) =>
    api.post<{ contact: CrmContact; created: boolean }>(`/crm/contacts/from-messaging/${chatId}`),
  updateContact: (id: string, body: Record<string, unknown>) =>
    api.patch<CrmContact>(`/crm/contacts/${id}`, body),
  deleteContact: (id: string) => api.delete(`/crm/contacts/${id}`),

  createDeal: (body: {
    title: string;
    value: string | number;
    stage_id?: string;
    contact_id?: string | null;
    expected_close_date?: string | null;
    notes?: string;
  }) => api.post<CrmDeal>("/crm/deals", body),
  updateDeal: (id: string, body: Record<string, unknown>) => api.patch<CrmDeal>(`/crm/deals/${id}`, body),
  deleteDeal: (id: string) => api.delete(`/crm/deals/${id}`),
  syncDealBudget: (id: string) =>
    api.post<{ deal_id: string; budget_income_id: string; amount: string; description: string }>(
      `/crm/deals/${id}/sync-budget`,
    ),
  createDealProject: (id: string) =>
    api.post<{ created: boolean; project: { id: string; name: string } }>(
      `/crm/deals/${id}/create-project`,
    ),

  activities: (params: { dealId?: string; contactId?: string }) => {
    const qs = new URLSearchParams();
    if (params.dealId) qs.set("deal_id", params.dealId);
    if (params.contactId) qs.set("contact_id", params.contactId);
    return api.get<CrmActivity[]>(`/crm/activities?${qs.toString()}`);
  },
  createActivity: (body: {
    body: string;
    kind: CrmActivity["kind"];
    deal_id?: string;
    contact_id?: string;
  }) => api.post<CrmActivity>("/crm/activities", body),
  toggleActivity: (id: string, done: boolean) => api.patch<CrmActivity>(`/crm/activities/${id}`, { done }),

  sources: () => api.get<DataSourceItem[]>("/crm/sources"),
  sourceRows: (id: string) =>
    api.get<{
      source: DataSourceItem;
      columns: ColumnDef[];
      rows: Record<string, unknown>[];
      total_rows: number;
    }>(`/crm/sources/${id}/rows`),
  previewPdf: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api.post<PdfPreviewResponse>("/crm/sources/preview/pdf", form);
  },
  previewCsv: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api.post<CsvPreviewResponse>("/crm/sources/preview/csv", form);
  },
  saveTabularSource: (body: {
    name: string;
    kind: "pdf" | "csv";
    description?: string;
    columns: ColumnDef[];
    rows: Record<string, unknown>[];
    source_id?: string | null;
    mode?: "replace" | "append";
    dedupe_key?: string | null;
    create_dashboard?: boolean;
  }) => api.post<{ source: DataSourceItem; dashboard: DashboardView | null }>("/crm/sources/tabular", body),
  importToCrm: (body: {
    target: "contacts" | "deals";
    rows: Record<string, unknown>[];
    mapping: Record<string, string>;
    origin?: string;
  }) => api.post<{ created: number; updated?: number; skipped: number }>("/crm/sources/import-to-crm", body),
  previewApi: (body: {
    url: string;
    method: "GET" | "POST";
    data_path?: string;
    auth_type: "none" | "bearer" | "api_key" | "basic";
    auth_value?: string;
    header_name?: string;
  }) => api.post<ApiPreviewResponse>("/crm/sources/preview/api", body),
  createApiSource: (body: {
    name: string;
    url: string;
    method: "GET" | "POST";
    data_path?: string;
    auth_type: "none" | "bearer" | "api_key" | "basic";
    auth_value?: string;
    header_name?: string;
    description?: string;
    sync_now?: boolean;
  }) => api.post<DataSourceItem>("/crm/sources/api", body),
  syncApiSource: (id: string) => api.post<DataSourceItem>(`/crm/sources/${id}/sync`),
  deleteSource: (id: string) => api.delete(`/crm/sources/${id}`),

  dashboards: () => api.get<DashboardSummary[]>("/crm/dashboards"),
  dashboard: (id: string, range: DateRangeKey) =>
    api.get<DashboardView>(`/crm/dashboards/${id}?date_range=${range}`),
  createDashboard: (body: {
    name: string;
    description?: string;
    template: DashboardTemplate;
    source_id?: string | null;
  }) => api.post<DashboardView>("/crm/dashboards", body),
  deleteDashboard: (id: string) => api.delete(`/crm/dashboards/${id}`),
  addWidget: (
    dashboardId: string,
    body: {
      source_id: string;
      title: string;
      widget_type: WidgetType;
      span: 1 | 2;
      query: Record<string, unknown>;
    },
  ) => api.post<DashboardView>(`/crm/dashboards/${dashboardId}/widgets`, body),
  deleteWidget: (widgetId: string) => api.delete(`/crm/widgets/${widgetId}`),
};

export function usePipeline() {
  return useQuery({ queryKey: crmKeys.pipeline, queryFn: crmApi.pipeline });
}

export function useContacts(q = "") {
  return useQuery({ queryKey: crmKeys.contacts(q), queryFn: () => crmApi.contacts(q) });
}

export function useHubMessagingChats(enabled = true) {
  return useQuery({
    queryKey: crmKeys.messagingChats,
    queryFn: crmApi.messagingChats,
    enabled,
    staleTime: 30_000,
  });
}

export function useSources() {
  return useQuery({ queryKey: crmKeys.sources, queryFn: crmApi.sources });
}

export function useDashboards() {
  return useQuery({ queryKey: crmKeys.dashboards, queryFn: crmApi.dashboards });
}

export function useDashboardView(id: string | null, range: DateRangeKey) {
  return useQuery({
    queryKey: id ? crmKeys.dashboard(id, range) : ["crm", "dashboard", "none"],
    queryFn: () => crmApi.dashboard(id!, range),
    enabled: Boolean(id),
  });
}
