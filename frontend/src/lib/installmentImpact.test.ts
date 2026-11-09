import { describe, expect, it } from "vitest";

import { cardCheck, cashCheck, installmentImpact, parcelMonths, parseNumber, safestCount, type ForecastMonth } from "./installmentImpact";

// Renda 6.200; parcelas que já existem 1.120/mês; sobra de dez a mai: 1150, 620, 890, 410, 980, 1240.
const leftover = [1150, 620, 890, 410, 980, 1240];
const months = ["2026-12", "2027-01", "2027-02", "2027-03", "2027-04", "2027-05"];
const forecast: ForecastMonth[] = months.map((month, i) => ({ month, income: 6200, expenses: 6200 - leftover[i]!, installments: 1120 }));

describe("parcelMonths", () => {
  it("lista os meses das parcelas a partir da 1ª, virando o ano", () => {
    expect(parcelMonths("2026-11", 3)).toEqual(["2026-11", "2026-12", "2027-01"]);
    expect(parcelMonths("2026-11", 0)).toEqual([]);
  });
});

describe("installmentImpact", () => {
  const impact = installmentImpact(forecast, 480, 6, "2026-12");

  it("soma a parcela à sobra prevista de cada mês", () => {
    expect(impact.months.map((m) => m.after)).toEqual([670, 140, 410, -70, 500, 760]);
    expect(impact.months.map((m) => m.before)).toEqual(leftover);
  });

  it("mostra quanto da renda fica comprometida com parcelas, antes e depois", () => {
    expect(impact.installmentsBefore).toBe(1120);
    expect(impact.installmentsAfter).toBe(1600);
    expect(impact.committedBefore).toBe(18.1);
    expect(impact.committedAfter).toBe(25.8);
  });

  it("aponta o mês de menor sobra, a sobra média e os meses negativos", () => {
    expect(impact.worst).toEqual({ month: "2027-03", before: 410, after: -70 });
    expect(impact.averageBefore).toBe(881.67);
    expect(impact.averageAfter).toBe(401.67);
    expect(impact.negativeMonths).toEqual(["2027-03"]);
    expect(impact.partial).toBe(false);
  });

  it("marca a previsão como parcial quando faltam meses ou receita", () => {
    expect(installmentImpact(forecast, 400, 12, "2026-12").partial).toBe(true);
    const noIncome = forecast.map((m) => ({ ...m, income: 0 }));
    const result = installmentImpact(noIncome, 400, 3, "2026-12");
    expect(result.partial).toBe(true);
    expect(result.committedAfter).toBeNull();
  });

  it("começa no mês escolhido para a 1ª parcela", () => {
    const later = installmentImpact(forecast, 480, 2, "2027-04");
    expect(later.months.map((m) => m.month)).toEqual(["2027-04", "2027-05"]);
  });
});

describe("safestCount", () => {
  it("acha o menor número de parcelas sem nenhum mês negativo", () => {
    // 4.800 em 6× = 800: jan e mar ficam negativos. Nenhuma opção de até 6 meses cabe aqui,
    // então com a previsão de 6 meses o resultado é nulo.
    expect(safestCount(forecast, 4800, "2026-12")).toBeNull();
    // 2.400 em 6× = 400: todos os meses ficam positivos (mar: 410 − 400 = 10).
    expect(safestCount(forecast, 2400, "2026-12")).toBe(6);
    // 1.100 de uma vez já cabe no 1º mês (sobra de 1.150).
    expect(safestCount(forecast, 1100, "2026-12")).toBe(1);
  });
});

describe("cardCheck", () => {
  it("o valor total da compra ocupa o limite", () => {
    expect(cardCheck(8000, 6200, 4800)).toEqual({ available: 6200, freeAfter: 1400, usedAfterPct: 82.5, fits: true });
    expect(cardCheck(8000, 3900, 4800)?.fits).toBe(false);
    expect(cardCheck(0, 0, 100)).toBeNull();
  });
});

describe("cashCheck", () => {
  it("diz se o saldo cobre o à vista sem usar a reserva", () => {
    expect(cashCheck(9200, 4416, 4500)).toMatchObject({ covers: true, leftover: 4784, coversWithReserve: false });
    expect(cashCheck(3000, 4416, 4500)).toMatchObject({ covers: false, missing: 1416, coversWithReserve: true });
    expect(cashCheck(100, 4416, 0).coversWithReserve).toBe(false);
  });
});

describe("parseNumber", () => {
  it("aceita vírgula e ponto do mesmo jeito", () => {
    expect(parseNumber("10,5")).toBe(10.5);
    expect(parseNumber("10.6")).toBe(10.6);
    expect(parseNumber("1.234,56")).toBe(1234.56);
    expect(parseNumber("8 %")).toBe(8);
    expect(parseNumber("")).toBe(0);
    expect(parseNumber("abc")).toBe(0);
  });
});
