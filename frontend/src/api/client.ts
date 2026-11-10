export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

let keepalive = false;

/*
 * v1.7.5: o que é enviado na saída da página (exclusão pendente ao recarregar ou fechar) fica
 * anotado neste aparelho até o servidor responder. Com o service worker ativo, o navegador às
 * vezes cancela esse último envio; na próxima abertura o app reenvia o que ficou anotado.
 */
const LEAVING_KEY = "envios-ao-sair";
const LEAVING_MAX_AGE = 10 * 60_000;
type Leaving = { id: string; method: string; path: string; body?: unknown; at: number };

function readLeaving(): Leaving[] {
  try {
    const list = JSON.parse(localStorage.getItem(LEAVING_KEY) ?? "[]");
    return Array.isArray(list) ? list : [];
  } catch {
    return [];
  }
}

function writeLeaving(list: Leaving[]) {
  try {
    if (list.length) localStorage.setItem(LEAVING_KEY, JSON.stringify(list.slice(-20)));
    else localStorage.removeItem(LEAVING_KEY);
  } catch {
    // Sem armazenamento: vale só o envio na saída.
  }
}

function noteLeaving(method: string, path: string, body: unknown): string {
  const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  writeLeaving([...readLeaving(), { id, method, path, body, at: Date.now() }]);
  return id;
}

function forgetLeaving(id: string) {
  writeLeaving(readLeaving().filter((item) => item.id !== id));
}

/** Reenvia o que ficou sem resposta ao sair da página. Devolve quantos envios foram refeitos. */
export async function resendLeaving(): Promise<number> {
  const list = readLeaving();
  if (list.length === 0) return 0;
  writeLeaving([]);
  let sent = 0;
  for (const item of list) {
    if (Date.now() - item.at > LEAVING_MAX_AGE) continue;
    try {
      await request(item.method, item.path, item.body);
      sent += 1;
    } catch {
      // Já tinha chegado (404: o item não existe mais) ou não vale mais: segue.
    }
  }
  return sent;
}

/**
 * Requisições iniciadas dentro de `fn` continuam mesmo se a página for recarregada ou fechada
 * (fetch com keepalive). Usado para confirmar uma exclusão pendente ao sair da página.
 */
export function withKeepalive<T>(fn: () => T): T {
  keepalive = true;
  try {
    return fn();
  } finally {
    keepalive = false;
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { "X-Requested-With": "fetch" };
  // Envio de arquivos (FormData): o navegador monta o Content-Type com o "boundary".
  const isForm = body instanceof FormData;
  if (body !== undefined && !isForm) headers["Content-Type"] = "application/json";

  const leaving = keepalive && !isForm && method !== "GET" ? noteLeaving(method, path, body) : null;
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      credentials: "include",
      headers,
      // Arquivos não cabem no limite do keepalive (64 KB); só requisições pequenas.
      keepalive: keepalive && !isForm,
      body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "network", "Sem conexão com o servidor. Tente novamente.");
  }
  // O servidor respondeu (com sucesso ou erro): não há o que reenviar.
  if (leaving) forgetLeaving(leaving);

  if (response.status === 204) return undefined as T;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(
      response.status,
      data?.error ?? "error",
      data?.message ?? `Erro inesperado (${response.status}).`,
    );
  }
  return data as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body: unknown = {}) => request<T>("POST", path, body),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
  put: <T>(path: string, body: unknown) => request<T>("PUT", path, body),
  delete: (path: string) => request<void>("DELETE", path),
  /** Envio com arquivos (multipart). */
  form: <T>(method: "POST" | "PUT", path: string, data: FormData) => request<T>(method, path, data),
  /** DELETE que devolve dados (ex.: perfil depois de remover a foto). */
  remove: <T>(path: string) => request<T>("DELETE", path),
};

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Algo deu errado.";
}
