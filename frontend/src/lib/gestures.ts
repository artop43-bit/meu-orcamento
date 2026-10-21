/** Regras dos gestos de toque, separadas da tela para poderem ser testadas. */

/** Quanto o dedo precisa andar (px) antes de decidir se o gesto é para o lado ou vertical. */
export const SLOP = 12;
/** Quanto puxar para baixo (px, já com a resistência) para atualizar. */
export const PULL_TRIGGER = 72;

/** Resistência elástica: quanto mais puxa, menos anda (como no iOS). Nunca passa de `limit`. */
export function rubberBand(distance: number, limit: number): number {
  const d = Math.abs(distance);
  return (Math.sign(distance) * (limit * d)) / (limit + d);
}

/**
 * "x" se o dedo andou claramente para o lado (pelo menos o dobro do vertical); "y" se não.
 * Diagonal conta como rolagem: rolar a página nunca troca de aba sem querer.
 */
export function gestureAxis(dx: number, dy: number): "x" | "y" | null {
  if (Math.abs(dx) < SLOP && Math.abs(dy) < SLOP) return null;
  return Math.abs(dx) > Math.abs(dy) * 2 ? "x" : "y";
}

/**
 * Ao soltar o dedo: troca de aba se arrastou mais de 1/3 da tela ou se foi um
 * movimento rápido. Retorna 1 (próxima aba, arrastou para a esquerda),
 * -1 (anterior) ou 0 (a tela volta para o lugar).
 */
export function swipeResult(dx: number, ms: number, width: number): -1 | 0 | 1 {
  const distance = Math.abs(dx);
  const velocity = distance / Math.max(ms, 1);
  const far = distance > width / 3;
  const flick = velocity > 0.45 && distance > 40;
  if (!far && !flick) return 0;
  return dx < 0 ? 1 : -1;
}

/** Aba vizinha na direção pedida, ou null se não houver (primeira/última, ou página fora das abas). */
export function neighbor<T>(items: readonly T[], index: number, dir: -1 | 1): T | null {
  if (index < 0) return null;
  return items[index + dir] ?? null;
}

/** Onde arrastar para o lado já tem outro uso: campos, controles deslizantes e áreas que rolam de lado. */
const NO_SWIPE = "input, textarea, select, [contenteditable], [data-no-swipe], dialog";

export function blocksSwipe(target: EventTarget | null, root: Element): boolean {
  let el = target instanceof Element ? target : null;
  while (el && el !== root) {
    if (el.matches(NO_SWIPE)) return true;
    if (el.scrollWidth > el.clientWidth + 1) {
      const overflow = getComputedStyle(el).overflowX;
      if (overflow === "auto" || overflow === "scroll") return true;
    }
    el = el.parentElement;
  }
  return false;
}
