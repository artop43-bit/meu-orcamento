import { api } from "./client";

export type ThreadKind = "idea" | "question" | "bug" | "praise" | "other";
export type ThreadStatus = "open" | "in_progress" | "planned" | "answered" | "resolved" | "declined";

export type Attachment = { id: string; width: number; height: number; content_type: string; filename?: string | null; size?: number };
export type Message = { id: string; from_admin: boolean; body: string; created_at: string; attachments: Attachment[] };
export type Thread = {
  id: string;
  /** Número fixo da solicitação (#1, #2...). */
  number: number;
  title: string;
  kind: ThreadKind;
  status: ThreadStatus;
  unread: boolean;
  created_at: string;
  last_message_at: string;
  status_note: string | null;
  planned_version: string | null;
  announcement_id: string | null;
};
export type ThreadDetail = Thread & { messages: Message[] };
export type Person = { id: string; email: string; display_name: string | null; avatar_id: string | null };
export type AdminThread = Thread & { user: Person; messages_count: number; page: string | null; app_version: string | null };
export type AdminThreadDetail = AdminThread & { user_agent: string | null; messages: Message[] };
export type PersonRow = { user: Person; total: number; open: number; unread: number; last_message_at: string };
export type SupportCounts = Record<ThreadStatus | "unread", number>;

/** Tema da solicitação (v1.3.1). */
export const KIND_LABEL: Record<ThreadKind, string> = { idea: "Sugestão", question: "Dúvida", bug: "Erro", praise: "Elogio", other: "Outro" };
export const STATUS_LABEL: Record<ThreadStatus, string> = {
  open: "Aberta",
  in_progress: "Em andamento",
  planned: "Planejada",
  answered: "Respondida",
  resolved: "Resolvida",
  declined: "Recusada",
};
export const STATUSES: ThreadStatus[] = ["open", "in_progress", "planned", "answered", "resolved", "declined"];

/** Limites iguais aos do servidor (conferidos lá também). */
export const MAX_IMAGES = 3;
export const MAX_IMAGE_MB = 5;
export const IMAGE_ACCEPT = "image/png,image/jpeg,image/webp,image/gif";
/** v1.3.1: anexos de mensagens também aceitam PDF e planilhas (o servidor confere o conteúdo). */
export const ATTACHMENT_ACCEPT = `${IMAGE_ACCEPT},application/pdf,.pdf,.xlsx,.xls,.csv,.ods`;
const DOCUMENT_EXTENSIONS = ["pdf", "xlsx", "xls", "csv", "ods"];

export function fileUrl(id: string): string {
  return `/api/files/${id}`;
}

function messageForm(message: string, images: File[], extra: Record<string, string> = {}): FormData {
  const form = new FormData();
  form.append("message", message);
  for (const [key, value] of Object.entries(extra)) form.append(key, value);
  for (const image of images) form.append("images", image, image.name);
  return form;
}

export const supportApi = {
  mine: () => api.get<Thread[]>("/support/threads"),
  unread: () => api.get<{ unread: number }>("/support/unread"),
  thread: (id: string) => api.get<ThreadDetail>(`/support/threads/${id}`),
  create: (data: { kind: ThreadKind; message: string; page?: string; app_version?: string }, images: File[]) =>
    api.form<Thread>(
      "POST",
      "/support/threads",
      messageForm(data.message, images, {
        kind: data.kind,
        ...(data.page ? { page: data.page } : {}),
        ...(data.app_version ? { app_version: data.app_version } : {}),
      }),
    ),
  reply: (id: string, message: string, images: File[]) =>
    api.form<ThreadDetail>("POST", `/support/threads/${id}/messages`, messageForm(message, images)),
  resolve: (id: string) => api.post<Thread>(`/support/threads/${id}/resolve`),

  adminThreads: (params: { q?: string; status?: ThreadStatus; user_id?: string; kind?: ThreadKind; version?: string }) => {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) if (value) query.set(key, value);
    const suffix = query.toString() ? `?${query}` : "";
    return api.get<AdminThread[]>(`/admin/support/threads${suffix}`);
  },
  adminPeople: (q?: string) => api.get<PersonRow[]>(`/admin/support/people${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  adminCounts: () => api.get<SupportCounts>("/admin/support/counts"),
  adminThread: (id: string) => api.get<AdminThreadDetail>(`/admin/support/threads/${id}`),
  adminReply: (id: string, message: string, images: File[]) =>
    api.form<AdminThreadDetail>("POST", `/admin/support/threads/${id}/messages`, messageForm(message, images)),
  adminStatus: (id: string, data: { status: ThreadStatus; note?: string | null; version?: string | null }) =>
    api.patch<AdminThreadDetail>(`/admin/support/threads/${id}`, data),
  adminVersions: () => api.get<string[]>("/admin/support/versions"),
};

/** Anexo de mensagem: imagem, PDF ou planilha, até 5 MB (o servidor confere o conteúdo). */
export function checkAttachment(file: File, maxMb = MAX_IMAGE_MB): string | null {
  const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
  if (extension === "xlsm") return `"${file.name}": planilhas com macros não são aceitas.`;
  if (!IMAGE_ACCEPT.split(",").includes(file.type) && !DOCUMENT_EXTENSIONS.includes(extension)) {
    return `"${file.name}": use imagem, PDF ou planilha (XLSX, XLS, CSV ou ODS).`;
  }
  if (file.size > maxMb * 1024 * 1024) return `"${file.name}" passa de ${maxMb} MB.`;
  return null;
}

export function isImage(attachment: { content_type: string }): boolean {
  return attachment.content_type.startsWith("image/");
}

/** Confere tipo e tamanho antes de enviar (o servidor confere de novo). */
export function checkImage(file: File, maxMb = MAX_IMAGE_MB): string | null {
  if (!IMAGE_ACCEPT.split(",").includes(file.type)) return `"${file.name}": use PNG, JPG, WebP ou GIF.`;
  if (file.size > maxMb * 1024 * 1024) return `"${file.name}" passa de ${maxMb} MB.`;
  return null;
}
