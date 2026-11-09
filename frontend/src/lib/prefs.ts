import { useSyncExternalStore } from "react";

import { isStyleName, type StyleName } from "../theme/styles";
import type { AccentName } from "../theme/tokens";

/**
 * Preferências deste aparelho (aparência e privacidade). Ficam no navegador: cada
 * celular/computador pode ter as suas. Aplicadas como atributos no <html>, então o CSS
 * reage sem recarregar a página.
 */
export type Prefs = {
  theme: "system" | "light" | "dark";
  accent: AccentName;
  /** v1.6: estilo visual (Padrão ou Liquid glass). */
  style: StyleName;
  text: "normal" | "grande" | "maior";
  density: "confortavel" | "compacta";
  /** Esconde os valores (R$ ••••) — útil em público ou ao mostrar a tela. */
  privacy: boolean;
  /** Abrir o app já com os valores escondidos. */
  privacyOnStart: boolean;
};

const KEY = "preferencias-v1";
const DEFAULTS: Prefs = {
  theme: "system",
  accent: "verde",
  style: "padrao",
  text: "normal",
  density: "confortavel",
  privacy: false,
  privacyOnStart: false,
};

function load(): Prefs {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) ?? "{}") as Partial<Prefs>;
    const prefs = { ...DEFAULTS, ...saved };
    if (!isStyleName(prefs.style)) prefs.style = DEFAULTS.style;
    return { ...prefs, privacy: prefs.privacyOnStart || prefs.privacy };
  } catch {
    return DEFAULTS;
  }
}

let current: Prefs = typeof window === "undefined" ? DEFAULTS : load();
const listeners = new Set<() => void>();

export function applyPrefs(prefs: Prefs = current) {
  const root = document.documentElement;
  if (prefs.theme === "system") root.removeAttribute("data-theme");
  else root.dataset.theme = prefs.theme;
  root.dataset.accent = prefs.accent;
  root.dataset.style = prefs.style;
  root.dataset.text = prefs.text;
  root.dataset.density = prefs.density;
  root.classList.toggle("privacy", prefs.privacy);
}

export function getPrefs(): Prefs {
  return current;
}

export function setPrefs(changes: Partial<Prefs>) {
  current = { ...current, ...changes };
  try {
    localStorage.setItem(KEY, JSON.stringify(current));
  } catch {
    // Navegação privada: vale só nesta aba.
  }
  applyPrefs(current);
  listeners.forEach((fn) => fn());
}

export function togglePrivacy(): boolean {
  setPrefs({ privacy: !current.privacy });
  return current.privacy;
}

function subscribe(fn: () => void) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function usePrefs(): Prefs {
  return useSyncExternalStore(subscribe, getPrefs, getPrefs);
}
