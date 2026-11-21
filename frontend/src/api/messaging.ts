import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";

import {
  mergeMessages,
  sessionPollInterval,
  type MessagesState,
  type ServiceStatus,
  type SessionStatusKey,
} from "../lib/messaging";
import { api, ApiError } from "./client";

export interface MessagingSession {
  status: SessionStatusKey;
  connected: boolean;
  /** O servidor tem o conector do WhatsApp configurado. */
  available: boolean;
  phone: string | null;
  /** Número formatado ("+55 (11) 99999-9999"); vazio quando não há número. */
  phone_display: string;
  display_name: string | null;
  /** Texto cru do QR Code (só com status "qr"); a tela desenha o código. */
  qr_code: string | null;
  pending_outbox: number;
  chats_count: number;
  unread_chats: number;
  last_seen_at: string | null;
  last_error: string | null;
  updated_at: string;
}

export interface MessagingChat {
  id: string;
  remote_jid: string;
  /** Nulo quando o WhatsApp esconde o número (contato só com LID). */
  phone: string | null;
  /** Número formatado; vazio quando não há número. */
  phone_display: string;
  lid_jid: string | null;
  name: string;
  avatar_url?: string | null;
  notes: string | null;
  budget_person: string | null;
  tags: string[];
  service_status: ServiceStatus;
  followup_at: string | null;
  followup_note: string | null;
  unread_count: number;
  pinned: boolean;
  archived: boolean;
  last_message_preview: string | null;
  last_message_at: string | null;
  created_at: string;
  updated_at: string;
}

export type MessageType = "chat" | "image" | "audio" | "video" | "document" | "sticker" | "other";

export interface MessagingMessage {
  id: string;
  chat_id: string;
  direction: "in" | "out";
  body: string;
  message_type: MessageType;
  status: "pending" | "sent" | "delivered" | "read" | "failed";
  external_id: string | null;
  reply_to_id: string | null;
  reply_preview: string | null;
  media_id?: string | null;
  media_mime?: string | null;
  media_name?: string | null;
  media_size?: number | null;
  media_url?: string | null;
  error_detail: string | null;
  sent_at: string | null;
  created_at: string;
  updated_at: string;
}

/** Resposta do GET de mensagens: os itens e o cursor para o próximo pedido (`since`). */
export interface MessagesPage {
  items: MessagingMessage[];
  cursor: string;
}

export type MessagesCache = MessagesState<MessagingMessage>;

export interface BudgetContact {
  person: string;
  phone: string | null;
  owes_me: string;
  i_owe: string;
  net: string;
  open_items: number;
}

export interface BudgetCategoryItem {
  id: string;
  name: string;
}

export interface BudgetContext {
  month: string;
  income_total: string;
  expense_total: string;
  pending_total: string;
  balance: string;
  pix_key?: string | null;
  pix_name?: string | null;
  contacts: BudgetContact[];
  linked_contact: BudgetContact | null;
  categories?: BudgetCategoryItem[];
  cards?: BudgetCategoryItem[];
}

export interface QuickReply {
  id: string;
  shortcut: string;
  title: string;
  body: string;
  created_at: string;
  updated_at: string;
}

export interface ChatCrmStage {
  id: string;
  name: string;
  position: number;
  is_won: boolean;
  is_lost: boolean;
}

export interface ChatCrmDeal {
  id: string;
  title: string;
  value: string;
  status: "open" | "won" | "lost";
  stage_id: string;
  stage_name: string;
  budget_income_id: string | null;
}

export interface ChatCrmContext {
  contact: {
    id: string;
    name: string;
    phone: string | null;
    phone_display: string | null;
    email: string | null;
    company: string | null;
    origin: string | null;
  } | null;
  deals: ChatCrmDeal[];
  stages: ChatCrmStage[];
}

export type ChatFilter =
  | "all"
  | "unread"
  | "followup"
  | "open"
  | "waiting"
  | "resolved"
  | "archived";

export const messagingKeys = {
  all: ["messaging"] as const,
  session: ["messaging", "session"] as const,
  chatLists: ["messaging", "chats"] as const,
  chats: (filter: ChatFilter = "all", q = "", tag = "") =>
    ["messaging", "chats", filter, q, tag] as const,
  chat: (chatId: string) => ["messaging", "chat", chatId] as const,
  messages: (chatId: string) => ["messaging", "messages", chatId] as const,
  budgetContext: (chatId?: string | null) => ["messaging", "budget-context", chatId ?? "all"] as const,
  crmContext: (chatId: string) => ["messaging", "crm-context", chatId] as const,
  quickReplies: ["messaging", "quick-replies"] as const,
};

export const messagingApi = {
  session: () => api.get<MessagingSession>("/messaging/session"),
  connect: () => api.post<MessagingSession>("/messaging/session/connect"),
  disconnect: () => api.post<MessagingSession>("/messaging/session/disconnect"),
  chats: (filter: ChatFilter = "all", q = "", tag = "") => {
    const params = new URLSearchParams({ filter });
    if (q.trim()) params.set("q", q.trim());
    if (tag.trim()) params.set("tag", tag.trim());
    return api.get<MessagingChat[]>(`/messaging/chats?${params.toString()}`);
  },
  chat: (chatId: string) => api.get<MessagingChat>(`/messaging/chats/${chatId}`),
  createChat: (body: { phone: string; name?: string; notes?: string; budget_person?: string }) =>
    api.post<MessagingChat>("/messaging/chats", body),
  updateChat: (
    chatId: string,
    body: {
      name?: string;
      notes?: string | null;
      budget_person?: string | null;
      pinned?: boolean;
      archived?: boolean;
      tags?: string[];
      service_status?: ServiceStatus;
      followup_at?: string | null;
      followup_note?: string | null;
    },
  ) => api.patch<MessagingChat>(`/messaging/chats/${chatId}`, body),
  deleteChat: (chatId: string) => api.delete(`/messaging/chats/${chatId}`),
  markRead: (chatId: string) => api.post<MessagingChat>(`/messaging/chats/${chatId}/read`),
  messages: (chatId: string, options: { since?: string | null; limit?: number } = {}) => {
    const params = new URLSearchParams({ limit: String(options.limit ?? 100) });
    if (options.since) params.set("since", options.since);
    return api.get<MessagesPage>(`/messaging/chats/${chatId}/messages?${params.toString()}`);
  },
  sendMessage: (chatId: string, body: { body: string; reply_to_id?: string | null }) =>
    api.post<MessagingMessage>(`/messaging/chats/${chatId}/messages`, body),
  sendMedia: (
    chatId: string,
    payload: { file: File; caption?: string; kind?: string; reply_to_id?: string | null },
  ) => {
    const form = new FormData();
    form.append("file", payload.file);
    if (payload.caption?.trim()) form.append("caption", payload.caption.trim());
    if (payload.kind) form.append("kind", payload.kind);
    if (payload.reply_to_id) form.append("reply_to_id", payload.reply_to_id);
    return api.post<MessagingMessage>(`/messaging/chats/${chatId}/media`, form);
  },
  budgetContext: (chatId?: string | null) => {
    const qs = chatId ? `?chat_id=${encodeURIComponent(chatId)}` : "";
    return api.get<BudgetContext>(`/messaging/budget-context${qs}`);
  },
  crmContext: (chatId: string) => api.get<ChatCrmContext>(`/messaging/chats/${chatId}/crm-context`),
  createCrmDeal: (
    chatId: string,
    body: { title: string; value?: string; stage_id?: string | null; notes?: string | null },
  ) => api.post<ChatCrmContext & { deal: ChatCrmDeal }>(`/messaging/chats/${chatId}/crm-deal`, body),
  createBudgetEntry: (
    chatId: string,
    body: {
      kind: "income" | "expense";
      description: string;
      amount: string;
      category_id?: string | null;
      card_id?: string | null;
      paid?: boolean;
      payment_method?: string | null;
      notes?: string | null;
      client_ref?: string | null;
    },
  ) =>
    api.post<{ id: string; kind: "income" | "expense"; month: string; description: string; amount: string }>(
      `/messaging/chats/${chatId}/budget-entry`,
      body,
    ),
  quickReplies: () => api.get<QuickReply[]>("/messaging/quick-replies"),
  createQuickReply: (body: { shortcut: string; title: string; body: string }) =>
    api.post<QuickReply>("/messaging/quick-replies", body),
  deleteQuickReply: (replyId: string) => api.delete(`/messaging/quick-replies/${replyId}`),
  workContext: (chatId: string) =>
    api.get<{
      projects: { id: string; name: string; status: string }[];
      projects_blocked: boolean;
      agenda_blocked: boolean;
    }>(`/messaging/chats/${chatId}/work-context`),
  createWorkTask: (
    chatId: string,
    body: {
      title: string;
      project_id?: string | null;
      message_id?: string | null;
      due_date?: string | null;
      priority?: "low" | "medium" | "high" | "urgent";
    },
  ) =>
    api.post<{ project_id: string; project_name: string }>(
      `/messaging/chats/${chatId}/work-task`,
      body,
    ),
  createAgendaEvent: (
    chatId: string,
    body: {
      title: string;
      kind?: "meeting" | "delivery" | "visit" | "reminder" | "personal";
      start_at: string;
      location?: string | null;
      notes?: string | null;
    },
  ) => api.post<{ id: string; title: string }>(`/messaging/chats/${chatId}/agenda-event`, body),
};

/** Erro de "não encontrado" não adianta repetir. */
function retryUnlessNotFound(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status === 404) return false;
  return failureCount < 3;
}

/**
 * Status da conexão com o WhatsApp.
 * `fast` = a janela de conexão está aberta: enquanto o pareamento anda (preparando ou QR),
 * pergunta a cada 2 s; no resto do tempo, a cada 10 s.
 */
export function useMessagingSession(fast = false) {
  return useQuery({
    queryKey: messagingKeys.session,
    queryFn: messagingApi.session,
    refetchInterval: (query) => sessionPollInterval(fast, query.state.data?.status),
  });
}

export function useMessagingChats(filter: ChatFilter, q: string, tag = "") {
  return useQuery({
    queryKey: messagingKeys.chats(filter, q, tag),
    queryFn: () => messagingApi.chats(filter, q, tag),
    refetchInterval: 8_000,
  });
}

/** Procura a conversa nas listas já carregadas (para o cabeçalho abrir na hora). */
function chatFromLists(queryClient: QueryClient, chatId: string): MessagingChat | undefined {
  for (const [, list] of queryClient.getQueriesData<MessagingChat[]>({ queryKey: messagingKeys.chatLists })) {
    const found = list?.find((item) => item.id === chatId);
    if (found) return found;
  }
  return undefined;
}

/**
 * A conversa aberta, buscada pelo id. Não depende do filtro nem da busca da lista:
 * arquivar ou buscar outra coisa não fecha a conversa.
 */
export function useMessagingChat(chatId: string | null) {
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: chatId ? messagingKeys.chat(chatId) : ["messaging", "chat", "none"],
    queryFn: () => messagingApi.chat(chatId!),
    enabled: Boolean(chatId),
    placeholderData: () => (chatId ? chatFromLists(queryClient, chatId) : undefined),
    refetchInterval: chatId ? 8_000 : false,
    retry: retryUnlessNotFound,
  });
}

/**
 * Mensagens da conversa com atualização incremental a cada 4 s: a primeira carga traz as mais
 * recentes; depois só pede o que mudou desde o cursor e mescla pelo id (status novo, mensagem nova).
 */
export function useMessagingMessages(chatId: string | null) {
  const queryClient = useQueryClient();
  return useQuery<MessagesCache>({
    queryKey: chatId ? messagingKeys.messages(chatId) : ["messaging", "messages", "none"],
    queryFn: async () => {
      const key = messagingKeys.messages(chatId!);
      const current = queryClient.getQueryData<MessagesCache>(key);
      if (!current?.cursor) {
        const page = await messagingApi.messages(chatId!);
        return mergeMessages(undefined, page.items, page.cursor);
      }
      const page = await messagingApi.messages(chatId!, { since: current.cursor });
      // Lê de novo: um envio pode ter entrado no cache enquanto o pedido estava no ar.
      const latest = queryClient.getQueryData<MessagesCache>(key) ?? current;
      return mergeMessages(latest, page.items, page.cursor);
    },
    enabled: Boolean(chatId),
    refetchInterval: chatId ? 4_000 : false,
    retry: retryUnlessNotFound,
  });
}

export function useBudgetContext(chatId?: string | null, enabled = true) {
  return useQuery({
    queryKey: messagingKeys.budgetContext(chatId),
    queryFn: () => messagingApi.budgetContext(chatId),
    enabled,
    staleTime: 30_000,
  });
}

export function useChatCrmContext(chatId: string | null, enabled = true) {
  return useQuery({
    queryKey: chatId ? messagingKeys.crmContext(chatId) : ["messaging", "crm-context", "none"],
    queryFn: () => messagingApi.crmContext(chatId!),
    enabled: Boolean(chatId) && enabled,
    staleTime: 15_000,
  });
}

export function useQuickReplies(enabled = true) {
  return useQuery({
    queryKey: messagingKeys.quickReplies,
    queryFn: messagingApi.quickReplies,
    enabled,
    staleTime: 60_000,
  });
}

export function useSendMessage(chatId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { body: string; reply_to_id?: string | null }) => messagingApi.sendMessage(chatId, payload),
    onSuccess: (message) => {
      // A mensagem enviada entra na hora (status "na fila"); o polling traz os próximos status.
      qc.setQueryData<MessagesCache>(messagingKeys.messages(chatId), (old) => mergeMessages(old, [message]));
      void qc.invalidateQueries({ queryKey: messagingKeys.chatLists });
      void qc.invalidateQueries({ queryKey: messagingKeys.chat(chatId) });
      void qc.invalidateQueries({ queryKey: messagingKeys.session });
    },
    onError: (error) => {
      // WhatsApp caiu no meio do caminho: atualiza o status para a tela pedir a conexão.
      if (error instanceof ApiError && error.status === 409) {
        void qc.invalidateQueries({ queryKey: messagingKeys.session });
      }
    },
  });
}

export function useSendMedia(chatId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { file: File; caption?: string; kind?: string; reply_to_id?: string | null }) =>
      messagingApi.sendMedia(chatId, payload),
    onSuccess: (message) => {
      qc.setQueryData<MessagesCache>(messagingKeys.messages(chatId), (old) => mergeMessages(old, [message]));
      void qc.invalidateQueries({ queryKey: messagingKeys.chatLists });
      void qc.invalidateQueries({ queryKey: messagingKeys.chat(chatId) });
      void qc.invalidateQueries({ queryKey: messagingKeys.session });
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status === 409) {
        void qc.invalidateQueries({ queryKey: messagingKeys.session });
      }
    },
  });
}
