import type { WebhookKind, WebhookService } from "../lib/webhook";
import { api } from "./client";

/** O servidor nunca devolve o endereço inteiro, só a dica ("discord.com/…a8F2"). */
export type WebhookConfig = {
  configured: boolean;
  hint: string | null;
  service: WebhookService | null;
  kinds: WebhookKind[];
  paused: boolean;
};

export const WEBHOOK_KEY = ["webhook"] as const;

export const webhookApi = {
  get: () => api.get<WebhookConfig>("/notifications/webhook"),
  save: (url: string) => api.put<WebhookConfig>("/notifications/webhook", { url }),
  kinds: (kinds: WebhookKind[]) => api.patch<WebhookConfig>("/notifications/webhook", { kinds }),
  test: () => api.post<{ ok: boolean }>("/notifications/webhook/test"),
  remove: () => api.delete("/notifications/webhook"),
};
