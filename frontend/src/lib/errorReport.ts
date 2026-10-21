import { RELEASE } from "../release";

/**
 * Painel de erros (v1.3): erros das telas vão para Administração › Erros, sem serviço externo.
 * Envia só tipo, mensagem, tela e as primeiras linhas da pilha; o servidor ainda mascara
 * números, e-mails e identificadores. No máximo 10 envios por visita, sem repetir o mesmo erro.
 */
const sent = new Set<string>();
const MAX = 10;

export function reportError(error: unknown, extra?: string) {
  const err = error instanceof Error ? error : new Error(typeof error === "string" ? error : "Erro desconhecido");
  const key = `${err.name}|${err.message}|${location.pathname}`;
  if (sent.has(key) || sent.size >= MAX) return;
  sent.add(key);
  const detail = [err.stack?.split("\n").slice(0, 6).join("\n"), extra?.split("\n").slice(0, 6).join("\n")].filter(Boolean).join("\n---\n");
  void fetch("/api/errors", {
    method: "POST",
    credentials: "include",
    keepalive: true,
    headers: { "Content-Type": "application/json", "X-Requested-With": "fetch" },
    body: JSON.stringify({
      name: err.name.slice(0, 80),
      message: err.message.slice(0, 300),
      path: location.pathname,
      release: RELEASE.version,
      detail: detail.slice(0, 4000) || null,
    }),
  }).catch(() => undefined);
}

/** Erros fora do React (scripts, promessas sem tratamento). Só no site publicado. */
export function installErrorReporting() {
  if (!import.meta.env.PROD) return;
  window.addEventListener("error", (event) => {
    // Falha ao carregar arquivo (sem internet) não é erro do app.
    if (!event.error) return;
    reportError(event.error);
  });
  window.addEventListener("unhandledrejection", (event) => {
    const reason = event.reason;
    // Erros de rede e da API já aparecem na tela para a pessoa; aqui só os inesperados.
    if (reason && typeof reason === "object" && "status" in reason) return;
    reportError(reason);
  });
}
