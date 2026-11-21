/** Utilitários puros da interface de Mensageria (datas, prévias, iniciais e estados). */
import { parseMoney } from "./format";

/** Anexos e textos externos pertencem somente à conversa que os recebeu. */
export function payloadForChat<T extends { chatId: string | null }>(payload: T | null, chatId: string): T | null {
  return payload?.chatId === chatId ? payload : null;
}

const DAY_MS = 86_400_000;

function startOfLocalDay(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

/** Rótulo curto na lista de conversas (hora hoje, "Ontem", ou dd/mm). */
export function formatChatTimestamp(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const diffDays = Math.round((startOfLocalDay(now) - startOfLocalDay(d)) / DAY_MS);
  if (diffDays === 0) return formatTime(iso);
  if (diffDays === 1) return "Ontem";
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
}

/** Rótulo do separador de data na linha do tempo de mensagens. */
export function formatMessageDay(iso: string, now: Date = new Date()): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const diffDays = Math.round((startOfLocalDay(now) - startOfLocalDay(d)) / DAY_MS);
  if (diffDays === 0) return "Hoje";
  if (diffDays === 1) return "Ontem";
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" });
}

export function dayKey(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** Limita a prévia em caracteres sem cortar com CSS overflow:hidden. */
export function shortenPreview(text: string | null | undefined, max = 56): string {
  const compact = (text ?? "").replace(/\s+/g, " ").trim();
  if (!compact) return "Sem mensagens";
  if (compact.length <= max) return compact;
  return `${compact.slice(0, max - 1).trimEnd()}…`;
}

export function contactInitials(name: string): string {
  const parts = name
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
}

export type SessionStatusKey = "disconnected" | "connecting" | "qr" | "ready" | "error";

export function sessionStatusLabel(status: SessionStatusKey): string {
  switch (status) {
    case "ready":
      return "Conectado";
    case "connecting":
      return "Conectando";
    case "qr":
      return "Aguardando QR";
    case "error":
      return "Erro";
    default:
      return "Desconectado";
  }
}

/** Cor do selo de status (classes `badge--*` que já existem). */
export function sessionBadgeTone(status: SessionStatusKey): string {
  switch (status) {
    case "ready":
      return "badge--ok";
    case "connecting":
    case "qr":
      return "badge--warn";
    case "error":
      return "badge--error";
    default:
      return "badge--muted";
  }
}

/** A conexão está no meio do pareamento (preparando ou mostrando o QR Code). */
export function isPairingStatus(status: SessionStatusKey | null | undefined): boolean {
  return status === "connecting" || status === "qr";
}

export const SESSION_POLL_FAST_MS = 2_000;
export const SESSION_POLL_SLOW_MS = 10_000;

/**
 * Intervalo de atualização do status da conexão: rápido (2 s) só com a janela de conexão aberta
 * e o pareamento em andamento, para o QR novo e o "Conectado" aparecerem logo; senão 10 s.
 */
export function sessionPollInterval(fast: boolean, status: SessionStatusKey | null | undefined): number {
  return fast && isPairingStatus(status) ? SESSION_POLL_FAST_MS : SESSION_POLL_SLOW_MS;
}

/** Texto do botão principal da janela de conexão, conforme o estado atual. */
export function connectButtonLabel(status: SessionStatusKey, lastError: string | null | undefined): string {
  if (status === "error") return "Tentar de novo";
  if (status === "disconnected" && lastError) return "Gerar novo QR";
  return "Conectar";
}

export const HIDDEN_PHONE_LABEL = "Número oculto pelo WhatsApp";

/** Número para mostrar na tela; contatos só com LID não têm número visível. */
export function chatPhoneLabel(chat: { phone?: string | null; phone_display?: string | null }): string {
  const display = (chat.phone_display ?? "").trim();
  if (display) return display;
  return HIDDEN_PHONE_LABEL;
}

export function hasVisiblePhone(chat: { phone?: string | null; phone_display?: string | null }): boolean {
  return Boolean((chat.phone_display ?? "").trim());
}

/* ---------------------------------------------------------- mensagens: polling incremental */

/** O mínimo que a mescla precisa saber de uma mensagem. */
export interface MergeableMessage {
  id: string;
  created_at: string;
  updated_at: string;
}

/** O que fica guardado no cache da conversa: as mensagens e o cursor do próximo pedido. */
export interface MessagesState<T extends MergeableMessage = MergeableMessage> {
  items: T[];
  cursor: string;
}

function timeOf(iso: string | null | undefined): number {
  if (!iso) return Number.NaN;
  return new Date(iso).getTime();
}

/** A data mais recente entre duas (texto ISO). Datas inválidas ou vazias são ignoradas. */
export function laterIso(a: string | null | undefined, b: string | null | undefined): string {
  const ta = timeOf(a);
  const tb = timeOf(b);
  if (Number.isNaN(ta)) return Number.isNaN(tb) ? "" : (b as string);
  if (Number.isNaN(tb)) return a as string;
  return tb > ta ? (b as string) : (a as string);
}

/**
 * Junta mensagens novas às que já estão na tela, pelo `id`: a versão mais recente (`updated_at`)
 * substitui a antiga, as novas entram, e tudo fica em ordem de `created_at`.
 * O cursor só avança quando vem um cursor do servidor (um envio local não mexe nele, para não
 * pular mensagens que ainda não chegaram).
 */
export function mergeMessages<T extends MergeableMessage>(
  current: MessagesState<T> | undefined,
  incoming: T[],
  cursor?: string | null,
): MessagesState<T> {
  const byId = new Map<string, T>();
  for (const item of current?.items ?? []) byId.set(item.id, item);
  for (const item of incoming) {
    const existing = byId.get(item.id);
    if (!existing) {
      byId.set(item.id, item);
      continue;
    }
    const newer = timeOf(item.updated_at);
    const older = timeOf(existing.updated_at);
    // Resposta atrasada de um pedido antigo não desfaz um status mais novo.
    if (Number.isNaN(older) || Number.isNaN(newer) || newer >= older) byId.set(item.id, item);
  }
  const items = [...byId.values()].sort((a, b) => {
    const diff = timeOf(a.created_at) - timeOf(b.created_at);
    return Number.isNaN(diff) ? 0 : diff;
  });
  return { items, cursor: laterIso(current?.cursor, cursor) };
}

/** Agrupa as mensagens por dia (para os separadores "Hoje", "Ontem", dd/mm/aaaa). */
export function groupMessagesByDay<T extends { created_at: string }>(
  messages: T[],
  now: Date = new Date(),
): { day: string; label: string; items: T[] }[] {
  const out: { day: string; label: string; items: T[] }[] = [];
  for (const msg of messages) {
    const key = dayKey(msg.created_at);
    const last = out[out.length - 1];
    if (!last || last.day !== key) {
      out.push({ day: key, label: formatMessageDay(msg.created_at, now), items: [msg] });
    } else {
      last.items.push(msg);
    }
  }
  return out;
}

export const MAX_MEDIA_BYTES = 8 * 1024 * 1024;

const MEDIA_PREFIXES: Record<string, string> = {
  image: "📷 Foto",
  audio: "🎤 Áudio",
  video: "🎬 Vídeo",
  document: "📄 Documento",
  sticker: "Figurinha",
};

/** Formata tamanho de arquivo em B, KB ou MB. */
export function formatBytes(bytes: number | null | undefined): string {
  if (!bytes || bytes <= 0) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1).replace(".", ",")} MB`;
}

/** Extrai apenas a legenda real quando a mídia já está sendo exibida no balão. */
export function mediaCaption(body: string, messageType: string, fileName?: string | null): string {
  const text = (body ?? "").trim();
  const prefix = MEDIA_PREFIXES[messageType];
  if (!prefix) return text;
  if (text === prefix) return "";
  if (!text.startsWith(prefix)) return text;
  const rest = text.slice(prefix.length).trim();
  if (!rest.startsWith("·")) return text;
  const after = rest.slice(1).trim();
  if (messageType === "document" && fileName) {
    if (after === fileName) return "";
    if (after.startsWith(fileName)) {
      const tail = after.slice(fileName.length).trim();
      return tail.startsWith("·") ? tail.slice(1).trim() : tail;
    }
  }
  return after;
}

/** Lê o arquivo escolhido para a memória (evita ERR_UPLOAD_FILE_CHANGED no Chrome/Windows). */
export async function snapshotFile(file: File): Promise<File> {
  if (typeof file.arrayBuffer === "function") {
    const buffer = await file.arrayBuffer();
    return new File([buffer], file.name, {
      type: file.type || "application/octet-stream",
      lastModified: file.lastModified,
    });
  }
  const buffer = await new Promise<ArrayBuffer>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as ArrayBuffer);
    reader.onerror = () => reject(reader.error ?? new Error("read_failed"));
    reader.readAsArrayBuffer(file);
  });
  return new File([buffer], file.name, {
    type: file.type || "application/octet-stream",
    lastModified: file.lastModified,
  });
}

export function messageStatusLabel(status: string): string {
  switch (status) {
    case "pending":
      return "Na fila";
    case "sent":
      return "Enviada";
    case "delivered":
      return "Entregue";
    case "read":
      return "Lida";
    case "failed":
      return "Falha no envio";
    default:
      return "Enviada";
  }
}

/* ---------------------------------------------------------- player de áudio, etiquetas e CRM 360° */

/** Formata segundos do player de áudio em `m:ss` (ex.: `0:05`, `1:42`). */
export function formatAudioTime(seconds: number | null | undefined): string {
  if (typeof seconds !== "number" || !Number.isFinite(seconds) || seconds <= 0) return "0:00";
  const total = Math.floor(seconds);
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  return `${mins}:${String(secs).padStart(2, "0")}`;
}

export type ServiceStatus = "open" | "waiting" | "resolved";

export const SERVICE_STATUS_LABELS: Record<ServiceStatus, string> = {
  open: "Em aberto",
  waiting: "Aguardando cliente",
  resolved: "Resolvido",
};

export function serviceStatusTone(status: ServiceStatus | string | null | undefined): string {
  if (status === "resolved") return "badge--ok";
  if (status === "waiting") return "badge--warn";
  return "badge--muted";
}

export const PRESET_CHAT_TAGS = [
  "Lead",
  "Cliente",
  "Orçamento",
  "Cobrança",
  "Urgente",
  "VIP",
] as const;

export interface FollowupBadge {
  label: string;
  tone: "overdue" | "today" | "upcoming";
}

/** Estado visual do follow-up agendado (atrasado, hoje ou futuro). */
export function followupStatus(
  iso: string | null | undefined,
  now: Date = new Date(),
): FollowupBadge | null {
  if (!iso) return null;
  const target = new Date(iso);
  if (Number.isNaN(target.getTime())) return null;
  const diffMs = target.getTime() - now.getTime();
  const diffDays = Math.round((startOfLocalDay(target) - startOfLocalDay(now)) / DAY_MS);
  const timeStr = formatTime(iso);
  if (diffMs < -60_000) {
    if (diffDays === 0) return { label: `Follow-up atrasado (${timeStr})`, tone: "overdue" };
    return {
      label: `Follow-up atrasado (${target.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })})`,
      tone: "overdue",
    };
  }
  if (diffDays === 0) {
    return { label: `Follow-up hoje ${timeStr}`, tone: "today" };
  }
  if (diffDays === 1) {
    return { label: `Follow-up amanhã ${timeStr}`, tone: "upcoming" };
  }
  return {
    label: `Follow-up ${target.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })}`,
    tone: "upcoming",
  };
}

export interface QuickReplyVars {
  nome?: string | null;
  telefone?: string | null;
  chave_pix?: string | null;
  valor_pendente?: string | null;
}

/** Substitui `{nome}`, `{telefone}`, `{chave_pix}` e `{valor_pendente}` no modelo de resposta rápida. */
export function expandQuickReply(template: string, vars: QuickReplyVars): string {
  const firstName = (vars.nome ?? "")
    .trim()
    .split(/\s+/)[0];
  const nome = firstName && firstName !== "Contato" ? firstName : (vars.nome ?? "").trim() || "tudo bem";
  const telefone = (vars.telefone ?? "").trim() || "";
  const chavePix = (vars.chave_pix ?? "").trim() || "(defina sua chave Pix em Meu Orçamento)";
  const valorPendente = (vars.valor_pendente ?? "").trim() || "R$ 0,00";

  return (template ?? "")
    .replace(/\{nome\}/gi, nome)
    .replace(/\{telefone\}/gi, telefone)
    .replace(/\{chave_pix\}/gi, chavePix)
    .replace(/\{valor_pendente\}/gi, valorPendente);
}

export interface ExtractedMoneyEntry {
  amount: string;
  kind: "income" | "expense";
  paymentMethod: "pix" | "credit" | "debit" | "boleto" | "cash";
  description: string;
}

/**
 * Extrai valor em reais (`R$ 150,00`, `150,50`, `200 reais`), tipo (receita/despesa) e
 * forma de pagamento do texto de uma mensagem do WhatsApp para pré-preencher o lançamento.
 */
export function extractMoneyFromMessage(
  rawBody: string,
  contactName?: string | null,
): ExtractedMoneyEntry {
  const clean = mediaCaption(rawBody, "image") || mediaCaption(rawBody, "document") || (rawBody ?? "").trim();
  const lower = clean.toLowerCase();

  let amount = "";
  const numberPattern = String.raw`(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{1,2}|\.\d{1,2})?`;
  const currencyMatch = clean.match(new RegExp(String.raw`r\$\s*(${numberPattern})(?![\d.,])`, "i"));
  const decimalMatch = clean.match(
    /\b(\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2})\b/,
  );
  const reaisWordMatch = clean.match(new RegExp(String.raw`\b(${numberPattern})\s*(?:reais|real|conto|pila)\b`, "i"));
  const milMatch = clean.match(new RegExp(String.raw`\b(${numberPattern})\s*mil\b`, "i"));

  const rawNum = milMatch?.[1] ?? currencyMatch?.[1] ?? decimalMatch?.[1] ?? reaisWordMatch?.[1] ?? "";
  if (rawNum) {
    const normalized = /^\d{1,3}(\.\d{3})+$/.test(rawNum) ? rawNum.replace(/\./g, "") : rawNum;
    const parsed = Number(parseMoney(normalized)) * (milMatch ? 1000 : 1);
    if (Number.isFinite(parsed) && parsed > 0) {
      amount = parsed.toFixed(2);
    }
  }

  const incomeHints = /\b(recebi|recebido|me\s+pagou|me\s+mandou|me\s+transferiu|entrada|venda|fechou|honor[aá]rio|mensalidade)\b/i;
  const kind: "income" | "expense" = incomeHints.test(lower) ? "income" : "expense";

  let paymentMethod: ExtractedMoneyEntry["paymentMethod"] = "pix";
  if (/\b(cr[eé]dito|cart[aã]o|parcelad)\b/i.test(lower)) paymentMethod = "credit";
  else if (/\b(d[eé]bito)\b/i.test(lower)) paymentMethod = "debit";
  else if (/\b(boleto)\b/i.test(lower)) paymentMethod = "boleto";
  else if (/\b(dinheiro|esp[eé]cie)\b/i.test(lower)) paymentMethod = "cash";

  const stripped = clean
    .replace(/^[📷🎤🎬📄]\s*(Foto|Áudio|Vídeo|Documento)\s*(·\s*)?/i, "")
    .replace(/r\$\s*\d[\d.,]*/gi, "")
    .replace(/\s+/g, " ")
    .trim();

  const fallbackDesc = contactName?.trim()
    ? `WhatsApp · ${contactName.trim()}`
    : "Lançamento via WhatsApp";
  const description = (stripped.length >= 3 ? stripped.slice(0, 90) : fallbackDesc).trim();

  return { amount, kind, paymentMethod, description };
}
