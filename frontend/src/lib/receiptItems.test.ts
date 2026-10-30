import { describe, expect, it } from "vitest";

import { itemsNote, partsFromItems } from "./receiptItems";

const item = (description: string, amount: string, category_id: string | null) => ({ description, amount, category_id });

describe("partsFromItems", () => {
  it("soma os produtos por categoria, do maior para o menor", () => {
    const items = [item("Arroz", "27.90", "food"), item("Detergente", "3.49", "home"), item("Feijão", "16.98", "food")];
    expect(partsFromItems(items)).toEqual([
      { categoryId: "food", amount: "44.88" },
      { categoryId: "home", amount: "3.49" },
    ]);
  });

  it("acima do limite de partes, o resto fica junto sem categoria", () => {
    const items = ["a", "b", "c", "d"].map((c, i) => item(c, String(10 - i), c));
    expect(partsFromItems(items, 3)).toEqual([
      { categoryId: "a", amount: "10.00" },
      { categoryId: "b", amount: "9.00" },
      { categoryId: "", amount: "15.00" },
    ]);
  });
});

describe("itemsNote", () => {
  it("lista nome e valor e corta no limite do campo", () => {
    const note = itemsNote([item("Arroz", "27.90", null), item("Feijão", "16.98", null)]);
    expect(note.replace(/\s/g, " ")).toBe("Itens: Arroz R$ 27,90; Feijão R$ 16,98");
    const long = itemsNote(Array.from({ length: 40 }, (_, i) => item(`Produto ${i}`, "1.00", null)), 120);
    expect(long.length).toBeLessThanOrEqual(120);
    expect(long.endsWith("…")).toBe(true);
  });
});
