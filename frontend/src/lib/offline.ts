import { useSyncExternalStore } from "react";

import { ApiError, api } from "../api/client";

/**
 * Lançamentos feitos sem internet (v1.3). Ficam numa fila neste aparelho e sobem sozinhos
 * quando a conexão volta (ao reconectar, ao abrir o app e a cada 30 s enquanto houver fila).
 *
 * Cada item leva um identificador gerado aqui (client_ref): se um envio chegar ao servidor e a
 * resposta se perder, o reenvio devolve o mesmo lançamento, sem duplicar.
 * Nesta versão a fila vale para criar despesas e receitas e para marcar como paga.
 */
export type QueuedItem = {
  id: string;
  kind: "expense" | "income" | "pay";
  path: string;
  method: "POST" | "PATCH";
  body: Record<string, unknown>;
  label: string;
  createdAt: string;
  /** Recusado pelo servidor (ex.: categoria apagada): fica para a pessoa ver e descartar. */
  error?: string;
};

const KEY = "fila-sem-internet-v1";
const listeners = new Set<() => void>();
// A fila é de cada pessoa: num aparelho com duas contas, um lançamento nunca vai para a outra.
let owner: string | null = null;
let items: QueuedItem[] = [];
let flushing = false;
let onSynced: (() => void) | null = null;

function load(): QueuedItem[] {
  if (!owner) return [];
  try {
    const saved = JSON.parse(localStorage.getItem(`${KEY}:${owner}`) ?? "[]");
    return Array.isArray(saved) ? saved : [];
  } catch {
    return [];
  }
}

/** Conta conectada neste aparelho (null ao sair). Carrega a fila dela e tenta enviar. */
export function setOfflineOwner(id: string | null) {
  if (id === owner) return;
  owner = id;
  items = load();
  listeners.forEach((listener) => listener());
  if (owner) void flush();
}

function save(next: QueuedItem[]) {
  items = next;
  if (!owner) return;
  try {
    localStorage.setItem(`${KEY}:${owner}`, JSON.stringify(items));
  } catch {
    // Sem armazenamento: a fila vale só enquanto a página estiver aberta.
  }
  listeners.forEach((listener) => listener());
}

// O app só roda em HTTPS (ou localhost), onde crypto.randomUUID existe.
const newId = () => crypto.randomUUID();

/** Falha de rede (sem resposta do servidor), e não um erro de validação. */
export function isNetworkError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 0;
}

/** Resultado de um envio que ficou na fila (sem internet). */
export type Queued = { queued: string };

export function isQueued(value: unknown): value is Queued {
  return typeof value === "object" && value !== null && "queued" in value;
}

/**
 * Envia agora; sem internet, guarda na fila e devolve { queued: id }. Quem chama mostra
 * "salvo no aparelho" (sem tratar como erro) e pode desfazer com discard(id).
 */
export async function sendOrQueue<T>(
  item: Omit<QueuedItem, "id" | "createdAt">,
  send: (clientRef: string) => Promise<T>,
): Promise<T | Queued> {
  const id = newId();
  if (!owner) return send(id);
  if (typeof navigator !== "undefined" && navigator.onLine === false) {
    enqueue({ ...item, id });
    return { queued: id };
  }
  try {
    return await send(id);
  } catch (error) {
    if (!isNetworkError(error)) throw error;
    enqueue({ ...item, id });
    return { queued: id };
  }
}

function enqueue(item: Omit<QueuedItem, "createdAt">) {
  // Marcar como paga: só o último pedido de cada despesa importa.
  const rest = item.kind === "pay" ? items.filter((i) => !(i.kind === "pay" && i.path === item.path)) : items;
  save([...rest, { ...item, createdAt: new Date().toISOString() }]);
}

export function discard(id: string) {
  save(items.filter((i) => i.id !== id));
}

/** Envia a fila em ordem. Para no primeiro problema de rede (tenta de novo depois). */
export async function flush(): Promise<number> {
  if (flushing || !owner || !items.some((i) => !i.error)) return 0;
  flushing = true;
  let sent = 0;
  try {
    for (const item of [...items]) {
      if (item.error) continue;
      const body = item.kind === "pay" ? item.body : { ...item.body, client_ref: item.id };
      try {
        if (item.method === "POST") await api.post(item.path, body);
        else await api.patch(item.path, body);
        save(items.filter((i) => i.id !== item.id));
        sent += 1;
      } catch (error) {
        // Rede, sessão expirada ou servidor fora: tenta de novo depois, sem descartar nada.
        if (isNetworkError(error) || (error instanceof ApiError && (error.status === 401 || error.status >= 500))) break;
        const message = error instanceof Error ? error.message : "Não foi possível enviar.";
        save(items.map((i) => (i.id === item.id ? { ...i, error: message } : i)));
      }
    }
  } finally {
    flushing = false;
  }
  if (sent) onSynced?.();
  return sent;
}

/** Liga o envio automático (uma vez, no início do app). `synced` recarrega as telas. */
export function startOfflineSync(synced: () => void) {
  onSynced = synced;
  const run = () => void flush();
  window.addEventListener("online", run);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") run();
  });
  window.setInterval(() => {
    if (items.some((i) => !i.error) && navigator.onLine !== false) run();
  }, 30_000);
  run();
}

export function useOfflineQueue(): QueuedItem[] {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => items,
  );
}

export const OFFLINE_SAVED = "Sem internet: lançamento guardado neste aparelho. Ele será enviado sozinho quando a conexão voltar.";
