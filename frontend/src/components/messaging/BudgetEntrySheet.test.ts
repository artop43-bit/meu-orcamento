import { describe, expect, it } from "vitest";

import { canSubmitBudgetEntry } from "./BudgetEntrySheet";

describe("Lançar no Meu Orçamento (trava de envio na Mensageria)", () => {
  const validBase = {
    description: "Site institucional",
    amount: "600,00",
    kind: "income" as const,
    paymentMethod: "pix",
    cardId: "",
    isPending: false,
    isSuccess: false,
  };

  it("libera o envio apenas quando os dados obrigatórios estão válidos e destravados", () => {
    expect(canSubmitBudgetEntry(validBase)).toBe(true);
    expect(canSubmitBudgetEntry({ ...validBase, description: "   " })).toBe(false);
    expect(canSubmitBudgetEntry({ ...validBase, amount: "" })).toBe(false);
    expect(canSubmitBudgetEntry({ ...validBase, amount: "0,00" })).toBe(false);
  });

  it("exige cartão na compra a crédito", () => {
    expect(
      canSubmitBudgetEntry({
        ...validBase,
        kind: "expense",
        paymentMethod: "credit",
        cardId: "",
      }),
    ).toBe(false);
    expect(
      canSubmitBudgetEntry({
        ...validBase,
        kind: "expense",
        paymentMethod: "credit",
        cardId: "card-1",
      }),
    ).toBe(true);
  });

  it("mantém o botão travado após salvar até reabrir a folha (reset da mutação)", () => {
    expect(canSubmitBudgetEntry({ ...validBase, isPending: true })).toBe(false);
    expect(canSubmitBudgetEntry({ ...validBase, isSuccess: true })).toBe(false);
  });
});
