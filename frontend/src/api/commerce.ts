import { useQuery } from "@tanstack/react-query";

import { api, ApiError } from "./client";

export type CatalogItemKind = "product" | "service";

export interface CatalogItem {
  id: string;
  kind: CatalogItemKind;
  sku: string | null;
  name: string;
  unit: string;
  cost_price: string;
  sale_price: string;
  unit_margin: string;
  margin_pct: string;
  stock_qty: string;
  min_stock: string;
  low_stock: boolean;
  active: boolean;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface CatalogSummary {
  total_items: number;
  active_products: number;
  active_services: number;
  low_stock_count: number;
  stock_cost_value: string;
  stock_sale_value: string;
}

export interface CatalogListResponse {
  items: CatalogItem[];
  summary: CatalogSummary;
}

export interface CatalogMovement {
  id: string;
  item_id: string;
  item_name: string;
  kind: "in" | "out" | "adjust";
  qty: string;
  reason: string | null;
  order_id: string | null;
  created_at: string;
}

export interface LineItemDraft {
  item_id?: string | null;
  kind?: CatalogItemKind;
  name: string;
  unit?: string;
  qty: number | string;
  unit_price: number | string;
  total?: number | string;
}

export interface CommercialOrder {
  id: string;
  number: number;
  contact_id: string | null;
  customer_name: string;
  items: LineItemDraft[];
  discount: string;
  total_amount: string;
  total_cost: string;
  gross_profit: string;
  status: "draft" | "confirmed" | "cancelled";
  crm_deal_id: string | null;
  budget_income_id: string | null;
  notes: string | null;
  warning?: string | null;
  created_at: string;
  updated_at: string;
}

export type CommercialDocType = "proposal" | "service_order" | "contract" | "receipt";

export interface CommercialDocument {
  id: string;
  doc_type: CommercialDocType;
  doc_label: string;
  number: number;
  title: string;
  contact_id: string | null;
  crm_deal_id: string | null;
  order_id: string | null;
  customer_name: string;
  customer_doc: string | null;
  customer_contact: string | null;
  items: LineItemDraft[];
  discount: string;
  total_amount: string;
  valid_until: string | null;
  terms_text: string | null;
  status: "draft" | "sent" | "approved" | "rejected" | "cancelled";
  budget_income_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface HubBridgeContact {
  id: string;
  name: string;
  phone: string | null;
  phone_display: string;
  email: string | null;
  messaging_chat_id: string | null;
}

export interface HubBridgeChat {
  id: string;
  name: string;
  phone: string | null;
  phone_display: string;
}

export interface HubBridgeDeal {
  id: string;
  title: string;
  value: string;
  status: string;
  contact_id: string | null;
}

export type StockMovementKind = "in" | "out" | "adjust";

export interface CatalogBridges {
  contacts: HubBridgeContact[];
  deals: HubBridgeDeal[];
}

export interface ProposalBridges {
  contacts: HubBridgeContact[];
  deals: HubBridgeDeal[];
  chats: HubBridgeChat[];
  catalog_items: CatalogItem[];
  orders: CommercialOrder[];
}

export const catalogKeys = {
  items: (kind = "all", q = "") => ["catalog", "items", kind, q] as const,
  movements: ["catalog", "movements"] as const,
  orders: ["catalog", "orders"] as const,
  bridges: ["catalog", "bridges"] as const,
};

export const proposalsKeys = {
  list: (docType = "all") => ["proposals", "list", docType] as const,
  bridges: ["proposals", "bridges"] as const,
};

export const catalogApi = {
  items: (params?: { kind?: CatalogItemKind | ""; q?: string }) => {
    const sp = new URLSearchParams();
    if (params?.kind) sp.set("kind", params.kind);
    if (params?.q) sp.set("q", params.q);
    const qs = sp.toString();
    return api.get<CatalogListResponse>(`/catalog/items${qs ? `?${qs}` : ""}`);
  },
  createItem: (body: {
    kind: CatalogItemKind;
    sku?: string;
    name: string;
    unit: string;
    cost_price: number;
    sale_price: number;
    stock_qty: number;
    min_stock: number;
    notes?: string;
  }) => api.post<CatalogItem>("/catalog/items", body),
  updateItem: (
    id: string,
    body: Partial<{
      kind: CatalogItemKind;
      sku: string | null;
      name: string;
      unit: string;
      cost_price: number | string;
      sale_price: number | string;
      min_stock: number | string;
      active: boolean;
      notes: string | null;
    }>,
  ) => api.patch<CatalogItem>(`/catalog/items/${id}`, body),
  deleteItem: (id: string) => api.delete(`/catalog/items/${id}`),
  moveStock: (id: string, body: { kind: StockMovementKind; qty: number; reason?: string }) =>
    api.post<CatalogItem>(`/catalog/items/${id}/movement`, body),
  movements: () => api.get<CatalogMovement[]>("/catalog/movements"),
  orders: () => api.get<CommercialOrder[]>("/catalog/orders"),
  createOrder: (body: {
    contact_id?: string | null;
    customer_name?: string;
    items: LineItemDraft[];
    discount: number;
    notes?: string;
    confirm_now: boolean;
    sync_budget: boolean;
    sync_crm: boolean;
  }) => api.post<CommercialOrder>("/catalog/orders", body),
  confirmOrder: (id: string, body: { sync_budget: boolean; sync_crm: boolean }) =>
    api.post<CommercialOrder>(`/catalog/orders/${id}/confirm`, body),
  cancelOrder: (id: string) => api.post<CommercialOrder>(`/catalog/orders/${id}/cancel`, {}),
  bridges: () => api.get<CatalogBridges>("/catalog/hub/bridges"),
};

export const proposalsApi = {
  list: (docType?: CommercialDocType | "all") => {
    const qs = docType && docType !== "all" ? `?doc_type=${encodeURIComponent(docType)}` : "";
    return api.get<CommercialDocument[]>(`/proposals${qs}`);
  },
  create: (body: {
    doc_type: CommercialDocType;
    title?: string;
    contact_id?: string | null;
    crm_deal_id?: string | null;
    order_id?: string | null;
    customer_name?: string;
    customer_doc?: string;
    customer_contact?: string;
    items: LineItemDraft[];
    discount: number;
    valid_until?: string | null;
    terms_text?: string;
  }) => api.post<CommercialDocument>("/proposals", body),
  update: (id: string, body: Partial<CommercialDocument>) =>
    api.patch<CommercialDocument>(`/proposals/${id}`, body),
  delete: (id: string) => api.delete(`/proposals/${id}`),
  sendToMessaging: (id: string, body: { chat_id: string; caption?: string }) =>
    api.post<{ document: CommercialDocument; message: Record<string, unknown> }>(
      `/proposals/${id}/send-messaging`,
      body,
    ),
  approve: (id: string, body: { sync_crm: boolean; sync_budget: boolean }) =>
    api.post<CommercialDocument>(`/proposals/${id}/approve`, body),
  createProject: (id: string) =>
    api.post<{ created: boolean; project: { id: string; name: string } }>(
      `/proposals/${id}/create-project`,
      {},
    ),
  bridges: () => api.get<ProposalBridges>("/proposals/hub/bridges"),
};

export async function downloadProposalPdf(docId: string, fallbackName: string): Promise<void> {
  const res = await fetch(`/api/proposals/${encodeURIComponent(docId)}/pdf`, {
    method: "GET",
    credentials: "include",
    headers: { "X-Requested-With": "fetch" },
  });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new ApiError(res.status, data?.error ?? "pdf_error", data?.message ?? "Não foi possível gerar o PDF.");
  }
  const blob = await res.blob();
  const disposition = res.headers.get("content-disposition") ?? "";
  const match = /filename="?([^"]+)"?/i.exec(disposition);
  const filename = match?.[1] ?? fallbackName;
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function useCatalogItems(kind: CatalogItemKind | "" = "", q = "") {
  return useQuery({
    queryKey: catalogKeys.items(kind || "all", q),
    queryFn: () => catalogApi.items({ kind, q }),
  });
}

export function useCatalogMovements() {
  return useQuery({
    queryKey: catalogKeys.movements,
    queryFn: catalogApi.movements,
  });
}

export function useCatalogOrders() {
  return useQuery({
    queryKey: catalogKeys.orders,
    queryFn: catalogApi.orders,
  });
}

export function useCatalogBridges(enabled = true) {
  return useQuery({
    queryKey: catalogKeys.bridges,
    queryFn: catalogApi.bridges,
    enabled,
  });
}

export function useProposals(docType: CommercialDocType | "all" = "all") {
  return useQuery({
    queryKey: proposalsKeys.list(docType),
    queryFn: () => proposalsApi.list(docType),
  });
}

export function useProposalBridges(enabled = true) {
  return useQuery({
    queryKey: proposalsKeys.bridges,
    queryFn: proposalsApi.bridges,
    enabled,
  });
}
