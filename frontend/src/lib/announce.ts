/**
 * Avisos para leitores de tela (NVDA, VoiceOver, TalkBack), escritos na região
 * "aria-live" que o Shell mantém na página.
 */
export function announce(message: string) {
  const region = document.getElementById("sr-announcer");
  if (!region) return;
  // Limpa e escreve no próximo quadro: assim até uma mensagem repetida é lida de novo.
  region.textContent = "";
  requestAnimationFrame(() => {
    region.textContent = message;
  });
}

export function prefersReducedMotion(): boolean {
  return typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
}
