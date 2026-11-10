import type { QueryClient } from "@tanstack/react-query";

import { ME_KEY, type User } from "../api/auth";
import { inboxApi } from "../api/inbox";
import { isStyleName } from "../theme/styles";
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
export type Appearance = Partial<Pick<Prefs, "theme" | "accent" | "style">>;

/** Ponto da tela de onde a revelação circular parte (o toque, ou o centro do elemento). */
export type Origin = { x: number; y: number };

export function originOf(event?: { clientX?: number; clientY?: number; currentTarget?: EventTarget | null; nativeEvent?: Event } | null): Origin | undefined {
  const native = event?.nativeEvent as MouseEvent | undefined;
  if (native && typeof native.clientX === "number" && (native.clientX || native.clientY)) return { x: native.clientX, y: native.clientY };
  const el = event?.currentTarget;
  if (el instanceof Element) {
    const r = el.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
  }
  return undefined;
}

type ViewTransitionDoc = Document & { startViewTransition?: (cb: () => void) => { ready: Promise<void> } };

/**
 * v1.6.5: aplica a troca com uma revelação circular a partir de `origin` (View Transitions do
 * navegador). Sem suporte, com "reduzir movimento", sem origem ou em navegador controlado por
 * teste automático, troca direto. (Com a revelação, a troca só acontece um quadro depois do
 * toque, quando o navegador termina de fotografar a tela antiga.)
 */
function withReveal(apply: () => void, origin?: Origin) {
  const doc = document as ViewTransitionDoc;
  const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  if (!origin || !doc.startViewTransition || reduce || navigator.webdriver) {
    apply();
    return;
  }
  const radius = Math.hypot(Math.max(origin.x, innerWidth - origin.x), Math.max(origin.y, innerHeight - origin.y));
  const transition = doc.startViewTransition(apply);
  transition.ready
    .then(() => {
      document.documentElement.animate(
        { clipPath: [`circle(0px at ${origin.x}px ${origin.y}px)`, `circle(${radius}px at ${origin.x}px ${origin.y}px)`] },
        { duration: 520, easing: "cubic-bezier(0.2, 0.8, 0.2, 1)", pseudoElement: "::view-transition-new(root)" },
      );
    })
    .catch(() => undefined);
}

export function setAppearance(changes: Appearance, queryClient?: QueryClient, origin?: Origin) {
  withReveal(() => setPrefs(changes), origin);
  queryClient?.setQueryData<User | null>(ME_KEY, (user) => (user ? { ...user, ...changes } : user));
  void inboxApi.appearance(changes).catch(() => undefined);
}

/** Ao entrar: a aparência salva na conta vale também neste aparelho. */
export function syncAppearance(user: Pick<User, "theme" | "accent" | "style">) {
  const current = getPrefs();
  const changes: Partial<Prefs> = {};
  if (user.theme && user.theme !== current.theme) changes.theme = user.theme;
  if (user.accent && user.accent !== current.accent) changes.accent = user.accent;
  if (user.style && isStyleName(user.style) && user.style !== current.style) changes.style = user.style;
  if (Object.keys(changes).length) setPrefs(changes);
}

/** Próximo tema do botão rápido: Automático → Claro → Escuro → Automático. */
export function nextTheme(theme: Prefs["theme"]): Prefs["theme"] {
  const order: Prefs["theme"][] = ["system", "light", "dark"];
  return order[(order.indexOf(theme) + 1) % order.length]!;
}
