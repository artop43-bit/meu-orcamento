/** Minúsculas e sem acento, para buscas ("Farmácia" acha "farmacia"). */
export function normalizeText(text: string): string {
  return text
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}
