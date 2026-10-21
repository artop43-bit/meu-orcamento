import { describe, expect, it } from "vitest";

import { parseQuickEntry } from "./quickEntry";
import { normalizeSpoken } from "./voice";

const TODAY = new Date(2026, 9, 21);

describe("lançamento por voz", () => {
  it("entende valores falados", () => {
    expect(normalizeSpoken("uber 23 reais e 50 centavos no débito")).toBe("uber 23,50 no débito");
    expect(normalizeSpoken("café 6 vírgula 5")).toBe("café 6,50");
    expect(normalizeSpoken("bala 50 centavos")).toBe("bala 0,50");
  });

  it("parcelas, cartão e receita", () => {
    expect(normalizeSpoken("geladeira 1800 em 10 vezes no cartão de crédito")).toBe("geladeira 1800 em 10x no crédito");
    expect(normalizeSpoken("Receita de freelance 600")).toBe("+ freelance 600");
  });

  it("a frase falada vira o mesmo lançamento da digitada", () => {
    const spoken = parseQuickEntry(normalizeSpoken("mercado R$ 120 reais pelo pix ontem"), TODAY);
    expect(spoken).toMatchObject({ description: "Mercado", amount: "120.00", payment: "pix", date: "2026-10-20" });
    const installments = parseQuickEntry(normalizeSpoken("geladeira 1800 em 10 vezes no cartão de crédito"), TODAY);
    expect(installments).toMatchObject({ description: "Geladeira", amount: "1800.00", installments: 10, payment: "credit" });
    const income = parseQuickEntry(normalizeSpoken("receita de freelance 600"), TODAY);
    expect(income).toMatchObject({ kind: "income", description: "Freelance", amount: "600.00" });
  });
});
