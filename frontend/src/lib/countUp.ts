/**
 * Números que "sobem" até o valor (v1.6.5). Separa o texto formatado em prefixo, número e
 * sufixo ("R$ 4.880,00", "-R$ 285,41", "73,7%") e reescreve o número durante a animação com
 * as mesmas casas decimais. Texto sem número (ex.: valores escondidos, "R$ ••••") não anima.
 */
export type Parsed = { prefix: string; value: number; decimals: number; suffix: string };

const NUMBER = /-?\d{1,3}(?:\.\d{3})+(?:,\d+)?|-?\d+(?:,\d+)?/;

export function parseFormatted(text: string): Parsed | null {
  const m = NUMBER.exec(text);
  if (!m) return null;
  const raw = m[0];
  const decimals = raw.includes(",") ? raw.split(",")[1]!.length : 0;
  const value = Number(raw.replace(/\./g, "").replace(",", "."));
  if (!Number.isFinite(value)) return null;
  return { prefix: text.slice(0, m.index), value, decimals, suffix: text.slice(m.index + raw.length) };
}

export function formatLike(parsed: Parsed, value: number): string {
  const n = value.toLocaleString("pt-BR", { minimumFractionDigits: parsed.decimals, maximumFractionDigits: parsed.decimals });
  return `${parsed.prefix}${n}${parsed.suffix}`;
}

/** Desaceleração no fim (rápido no começo, assenta suave). */
export const easeOut = (t: number) => 1 - (1 - t) ** 3;

/** Animar? Não com "reduzir movimento" nem em testes automáticos (o número aparece direto). */
export function shouldAnimate(): boolean {
  if (typeof window === "undefined") return false;
  if (navigator.webdriver) return false;
  return !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}
