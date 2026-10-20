import type { QueryClient } from "@tanstack/react-query";

import { ME_KEY, type User } from "../api/auth";
import { inboxApi } from "../api/inbox";
import { getPrefs, setPrefs, type Prefs } from "./prefs";

export const THEMES: [Prefs["theme"], string][] = [
  ["system", "Automático"],
  ["light", "Claro"],
  ["dark", "Escuro"],
];

/**
 * Tema e cor de destaque: aplicados na hora neste aparelho e salvos na conta, para valerem
 * em qualquer aparelho em que a pessoa entrar. Falha ao salvar não desfaz a escolha local.
 */
export function setAppearance(changes: Partial<Pick<Prefs, "theme" | "accent">>, queryClient?: QueryClient) {
  setPrefs(changes);
  queryClient?.setQueryData<User | null>(ME_KEY, (user) => (user ? { ...user, ...changes } : user));
  void inboxApi.appearance(changes).catch(() => undefined);
}

/** Ao entrar: a aparência salva na conta vale também neste aparelho. */
export function syncAppearance(user: Pick<User, "theme" | "accent">) {
  const current = getPrefs();
  const changes: Partial<Prefs> = {};
  if (user.theme && user.theme !== current.theme) changes.theme = user.theme;
  if (user.accent && user.accent !== current.accent) changes.accent = user.accent;
  if (Object.keys(changes).length) setPrefs(changes);
}

/** Próximo tema do botão rápido: Automático → Claro → Escuro → Automático. */
export function nextTheme(theme: Prefs["theme"]): Prefs["theme"] {
  const order: Prefs["theme"][] = ["system", "light", "dark"];
  return order[(order.indexOf(theme) + 1) % order.length]!;
}
