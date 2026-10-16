/**
 * Vibração curta de resposta ao toque (Android). Onde não há suporte
 * (iPhone, desktop), não faz nada.
 */
const PATTERNS = { tap: 8, success: [10, 40, 16], error: [24, 60, 24] } as const;

export function haptic(kind: keyof typeof PATTERNS = "tap") {
  if (typeof navigator === "undefined" || typeof navigator.vibrate !== "function") return;
  try {
    navigator.vibrate(PATTERNS[kind] as number | number[]);
  } catch {
    // Alguns navegadores bloqueiam a vibração fora de um toque do usuário.
  }
}
