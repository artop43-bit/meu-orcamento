import { describe, expect, it } from "vitest";

import { defaultEntryDate, looksLikeEntry, looksLikeQuestion, parseQuickEntry } from "./quickEntry";

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

describe("núcleo de linguagem compartilhado (v1.7.6)", () => {
  // 22/01/2030 é uma terça-feira.
  it("verbos de lançamento saem da descrição", () => {
    expect(parseQuickEntry("gastei 50 no mercado", TODAY)).toMatchObject({ kind: "expense", description: "Mercado", amount: "50.00" });
    expect(parseQuickEntry("paguei 200 de luz hoje", TODAY)).toMatchObject({ description: "Luz", amount: "200.00", date: "2030-01-22" });
    expect(parseQuickEntry("lançar uber 30", TODAY)).toMatchObject({ description: "Uber", amount: "30.00" });
    expect(parseQuickEntry("comprei um tênis por 350 no crédito", TODAY)).toMatchObject({
      description: "Tênis",
      amount: "350.00",
      payment: "credit",
    });
    expect(parseQuickEntry("pedi ifood 45", TODAY).description).toBe("Ifood");
    expect(parseQuickEntry("despesa farmácia 80", TODAY).description).toBe("Farmácia");
    expect(parseQuickEntry("anota aí: padaria 12", TODAY)).toMatchObject({ description: "Padaria", amount: "12.00" });
  });

  it("quando o verbo é a frase toda, vira o nome do gasto", () => {
    expect(parseQuickEntry("almocei 35", TODAY)).toMatchObject({ description: "Almoço", amount: "35.00" });
    expect(parseQuickEntry("abasteci 180 no débito", TODAY)).toMatchObject({ description: "Combustível", payment: "debit" });
    expect(looksLikeEntry(parseQuickEntry("gastei 50", TODAY))).toBe(false);
  });

  it("formas de pagamento com mais de uma palavra", () => {
    expect(parseQuickEntry("mercado 120 no cartão de crédito", TODAY)).toMatchObject({ description: "Mercado", payment: "credit" });
    expect(parseQuickEntry("farmácia 42 cartão de débito ontem", TODAY)).toMatchObject({
      description: "Farmácia",
      payment: "debit",
      date: "2030-01-21",
    });
    expect(parseQuickEntry("feira 60 em dinheiro", TODAY)).toMatchObject({ description: "Feira", payment: "cash" });
    expect(parseQuickEntry("aluguel 1500 boleto", TODAY).payment).toBe("boleto");
  });

  it("valores falados: mil, k, reais, conto", () => {
    expect(parseQuickEntry("recebi 3 mil de salário", TODAY)).toMatchObject({ kind: "income", description: "Salário", amount: "3000.00" });
    expect(parseQuickEntry("notebook 4,5k", TODAY).amount).toBe("4500.00");
    expect(parseQuickEntry("gastei 50 reais no mercado", TODAY)).toMatchObject({ description: "Mercado", amount: "50.00" });
    expect(parseQuickEntry("uber 20 reais corrida pro trabalho", TODAY).description).toBe("Uber corrida pro trabalho");
    expect(parseQuickEntry("lanche 15 conto", TODAY)).toMatchObject({ description: "Lanche", amount: "15.00" });
    expect(parseQuickEntry("café R$ 8", TODAY)).toMatchObject({ description: "Café", amount: "8.00" });
    expect(parseQuickEntry("mercado 120, pix", TODAY)).toMatchObject({ description: "Mercado", amount: "120.00", payment: "pix" });
  });

  it("datas faladas: anteontem, amanhã e dia da semana", () => {
    expect(parseQuickEntry("pizza 60 antes de ontem", TODAY).date).toBe("2030-01-20");
    expect(parseQuickEntry("luz 180 amanhã", TODAY).date).toBe("2030-01-23");
    expect(parseQuickEntry("paguei 200 de luz na sexta", TODAY)).toMatchObject({ description: "Luz", date: "2030-01-18" });
    expect(parseQuickEntry("cinema 40 segunda-feira", TODAY).date).toBe("2030-01-21");
    expect(parseQuickEntry("mercado 90 terça", TODAY).date).toBe("2030-01-22");
    // "segunda via" não é uma data.
    expect(parseQuickEntry("segunda via do rg 50", TODAY)).toMatchObject({ description: "Segunda via do rg", date: null });
  });

  it("parcelas por extenso", () => {
    expect(parseQuickEntry("sofá 2400 em 12 vezes no crédito", TODAY)).toMatchObject({
      description: "Sofá",
      installments: 12,
      payment: "credit",
    });
    expect(parseQuickEntry("celular 3000 10 parcelas", TODAY).installments).toBe(10);
  });

  it("receita pelo nome ou pelo verbo", () => {
    expect(parseQuickEntry("salário 3000", TODAY)).toMatchObject({ kind: "income", description: "Salário" });
    expect(parseQuickEntry("freela 600 pix", TODAY)).toMatchObject({ kind: "income", description: "Freela", payment: "pix" });
    expect(parseQuickEntry("caiu 850 de reembolso", TODAY)).toMatchObject({ kind: "income", description: "Reembolso" });
    expect(parseQuickEntry("recebi 500", TODAY)).toMatchObject({ kind: "income", description: "Receita", amount: "500.00" });
    expect(parseQuickEntry("aluguel 1500", TODAY).kind).toBe("expense");
  });

  it("pergunta não é lançamento", () => {
    expect(looksLikeQuestion("quanto gastei este mês?")).toBe(true);
    expect(looksLikeQuestion("qual ano mais gastei")).toBe(true);
    expect(looksLikeQuestion("onde encontro as metas")).toBe(true);
    expect(looksLikeQuestion("o que vence hoje")).toBe(true);
    expect(looksLikeQuestion("mostra meus gastos")).toBe(true);
    expect(looksLikeQuestion("total do mês")).toBe(true);
    expect(looksLikeQuestion("gastei 50 no mercado?")).toBe(true);
    expect(looksLikeQuestion("mercado 120 pix ontem")).toBe(false);
    expect(looksLikeQuestion("gastei 50 no mercado")).toBe(false);
    expect(looksLikeQuestion("+ freelance 600")).toBe(false);
    expect(looksLikeQuestion("total 50")).toBe(false);
    expect(looksLikeQuestion("")).toBe(false);
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
