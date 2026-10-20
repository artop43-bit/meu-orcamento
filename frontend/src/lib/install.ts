import { useSyncExternalStore } from "react";

/**
 * Convite de instalação do navegador (Chrome/Edge no computador e no Android).
 * O evento `beforeinstallprompt` chega uma vez, logo depois de a página abrir: se ninguém
 * estiver ouvindo naquela hora, ele se perde. Por isso é capturado no início do app
 * (main.tsx) e guardado aqui até a tela "App e notificações" usar.
 */
export type InstallPrompt = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: string }> };

let pending: InstallPrompt | null = null;
const listeners = new Set<() => void>();

function emit() {
  for (const listener of listeners) listener();
}

export function captureInstallPrompt() {
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    pending = event as InstallPrompt;
    emit();
  });
  window.addEventListener("appinstalled", () => {
    pending = null;
    emit();
  });
}

export function useInstallPrompt(): InstallPrompt | null {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => pending,
  );
}

/** Abre o convite; devolve true se a pessoa aceitou. O convite só vale uma vez. */
export async function promptInstall(): Promise<boolean> {
  const prompt = pending;
  if (!prompt) return false;
  pending = null;
  emit();
  await prompt.prompt();
  const { outcome } = await prompt.userChoice;
  return outcome === "accepted";
}
