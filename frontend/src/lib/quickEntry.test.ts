import { describe, expect, it } from "vitest";

import { defaultEntryDate, looksLikeEntry, parseQuickEntry } from "./quickEntry";

const TODAY = new Date(2030, 0, 22); // 22/01/2030

describe("parseQuickEntry", () => {
  it("entende valor, forma de pagamento e ontem", () => {
    expect(parseQuickEntry("mercado 120 pix ontem", TODAY)).toEqual({
      kind: "expense",
      description: "Mercado",
      amount: "120.00",
      date: "2030-01-21",
      payment: "pix",
      installments: null,
    });
  });

  it("valores com vírgula, milhar e R$", () => {
    expect(parseQuickEntry("uber 23,50 débito", TODAY).amount).toBe("23.50");
    expect(parseQuickEntry("tv 1.990,00", TODAY).amount).toBe("1990.00");
    expect(parseQuickEntry("café R$8", TODAY).amount).toBe("8.00");
  });

  it("parcelas, crédito e dia do mês", () => {
    const entry = parseQuickEntry("geladeira 3000 10x crédito dia 5", TODAY);
    expect(entry).toMatchObject({ description: "Geladeira", installments: 10, payment: "credit", date: "2030-01-05" });
  });

  it("“em 10x”: o valor é o total da compra", () => {
    expect(parseQuickEntry("geladeira 1800 em 10x", TODAY)).toMatchObject({
      description: "Geladeira",
      amount: "1800.00",
      installments: 10,
    });
  });

  it("data no formato dd/mm", () => {
    expect(parseQuickEntry("farmácia 42 15/01", TODAY).date).toBe("2030-01-15");
  });

  it("renda com + ou 'recebi'", () => {
    expect(parseQuickEntry("+ freelance 600", TODAY)).toMatchObject({ kind: "income", description: "Freelance", amount: "600.00" });
    expect(parseQuickEntry("recebi comissão 250", TODAY)).toMatchObject({ kind: "income", description: "Comissão" });
  });

  it("descrição com várias palavras e preposições", () => {
    expect(parseQuickEntry("almoço no restaurante 45 no débito", TODAY).description).toBe("Almoço no restaurante");
  });

  it("sem valor não é lançamento", () => {
    expect(looksLikeEntry(parseQuickEntry("calendário", TODAY))).toBe(false);
    expect(looksLikeEntry(parseQuickEntry("pão 8", TODAY))).toBe(true);
  });

  it("mês aberto na tela: “dia 5” cai nele", () => {
    expect(parseQuickEntry("luz 180 dia 5", TODAY, "2030-03").date).toBe("2030-03-05");
    expect(parseQuickEntry("luz 180", TODAY, "2030-03").date).toBeNull();
  });
});

describe("defaultEntryDate", () => {
  it("hoje no mês atual; dia 1 do mês aberto se for outro", () => {
    expect(defaultEntryDate(undefined, TODAY)).toBe("2030-01-22");
    expect(defaultEntryDate("2030-01", TODAY)).toBe("2030-01-22");
    expect(defaultEntryDate("2030-03", TODAY)).toBe("2030-03-01");
    expect(defaultEntryDate("2029-12", TODAY)).toBe("2029-12-01");
  });
});
