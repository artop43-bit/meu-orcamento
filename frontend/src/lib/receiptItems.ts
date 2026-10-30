import type { ReceiptItem } from "../api/budget";
import { money } from "./format";

export type ItemPart = { categoryId: string; amount: string };

/**
 * Produtos do cupom agrupados pela categoria sugerida, do maior valor para o menor (v1.5).
 * A despesa aceita até `max` partes: o que passar disso fica junto, sem categoria, para a
 * pessoa escolher.
 */
export function partsFromItems(items: ReceiptItem[], max = 6): ItemPart[] {
  const totals = new Map<string, number>();
  for (const item of items) {
    const key = item.category_id ?? "";
    totals.set(key, (totals.get(key) ?? 0) + Number(item.amount));
  }
  const sorted = [...totals.entries()].sort((a, b) => b[1] - a[1]);
  if (sorted.length > max) {
    const rest = sorted.splice(max - 1).reduce((sum, [, value]) => sum + value, 0);
    const blank = sorted.findIndex(([key]) => key === "");
    if (blank >= 0) sorted[blank]![1] += rest;
    else sorted.push(["", rest]);
  }
  return sorted.map(([categoryId, value]) => ({ categoryId, amount: value.toFixed(2) }));
}

/** Lista dos produtos para a observação da despesa (cabe nos 500 caracteres do campo). */
export function itemsNote(items: ReceiptItem[], limit = 500): string {
  let note = "Itens:";
  for (const [index, item] of items.entries()) {
    const next = `${index ? ";" : ""} ${item.description} ${money(item.amount)}`;
    if (note.length + next.length > limit - 2) return `${note}…`;
    note += next;
  }
  return note;
}
