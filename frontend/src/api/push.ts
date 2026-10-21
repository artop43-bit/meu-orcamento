import { api } from "./client";

export type PushConfig = {
  enabled: boolean;
  public_key: string;
  devices: number;
  push_due: boolean;
  push_messages: boolean;
  push_alerts: boolean;
  push_weekly: boolean;
};

export const PUSH_KEY = ["push"] as const;

export const pushApi = {
  config: () => api.get<PushConfig>("/push"),
  subscribe: (sub: PushSubscriptionJSON) => api.post<PushConfig>("/push/subscribe", sub),
  unsubscribe: (endpoint: string) => api.post<PushConfig>("/push/unsubscribe", { endpoint }),
  prefs: (data: Partial<Pick<PushConfig, "push_due" | "push_messages" | "push_alerts" | "push_weekly">>) => api.patch<PushConfig>("/push/prefs", data),
  test: () => api.post<{ sent: number }>("/push/test"),
};

/** Chave pública VAPID (base64url) no formato que o navegador espera. */
function keyBytes(base64url: string): Uint8Array {
  const pad = "=".repeat((4 - (base64url.length % 4)) % 4);
  const raw = atob((base64url + pad).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

export function pushSupported(): boolean {
  return typeof window !== "undefined" && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

export async function currentSubscription(): Promise<PushSubscription | null> {
  if (!pushSupported()) return null;
  const registration = await navigator.serviceWorker.getRegistration();
  return (await registration?.pushManager.getSubscription()) ?? null;
}

/** Pede a permissão, inscreve este aparelho e registra no servidor. */
export async function enablePush(publicKey: string): Promise<PushConfig> {
  const permission = await Notification.requestPermission();
  if (permission !== "granted") throw new Error("Permissão negada. Libere as notificações do Meu Orçamento nas configurações do aparelho.");
  const registration = await navigator.serviceWorker.ready;
  const subscription =
    (await registration.pushManager.getSubscription()) ??
    (await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(publicKey) as BufferSource }));
  return pushApi.subscribe(subscription.toJSON());
}

export async function disablePush(): Promise<PushConfig | null> {
  const subscription = await currentSubscription();
  if (!subscription) return null;
  const config = await pushApi.unsubscribe(subscription.endpoint);
  await subscription.unsubscribe();
  return config;
}
