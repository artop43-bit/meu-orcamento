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
  delete: (path: string) => request<void>("DELETE", path),
  /** Envio com arquivos (multipart). */
  form: <T>(method: "POST" | "PUT", path: string, data: FormData) => request<T>(method, path, data),
  /** DELETE que devolve dados (ex.: perfil depois de remover a foto). */
  remove: <T>(path: string) => request<T>("DELETE", path),
};

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Algo deu errado.";
}
