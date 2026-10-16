import { describe, expect, it } from "vitest";

import { cumulativeBalance, simulate, ZERO_SIM } from "./simulate";

const october = { income: 4500, expenses: 3050 };

describe("simulate", () => {
  it("sem mudanças, devolve o mês real", () => {
    expect(simulate(october, 750, ZERO_SIM)).toEqual({ income: 4500, expenses: 3050, balance: 1450 });
  });

  it("combina renda, corte nos não essenciais e nova conta", () => {
    // Mesmo cenário conferido à mão no navegador: +10% de renda, -50% em desejos, +R$ 600.
    const result = simulate(october, 750, { incomePct: 10, expensePct: 0, cutWantsPct: 50, extra: 600 });
    expect(result.income).toBeCloseTo(4950);
    expect(result.expenses).toBeCloseTo(3275);
    expect(result.balance).toBeCloseTo(1675);
  });

  it("aplica a variação geral depois do corte", () => {
    const result = simulate({ income: 1000, expenses: 1000 }, 200, {
      incomePct: 0,
      expensePct: 10,
      cutWantsPct: 100,
      extra: 0,
    });
    expect(result.expenses).toBeCloseTo(880); // (1000 - 200) * 1,1
  });

  it("nunca deixa as contas negativas", () => {
    const result = simulate({ income: 1000, expenses: 100 }, 100, {
      incomePct: 0,
      expensePct: -50,
      cutWantsPct: 100,
      extra: 0,
    });
    expect(result.expenses).toBe(0);
  });
});

describe("cumulativeBalance", () => {
  it("acumula o saldo usando os não essenciais de cada mês", () => {
    const months = [
      { income: 4500, expenses: 3050, nonEssential: 750 },
      { income: 4500, expenses: 1700, nonEssential: 300 },
      { income: 4500, expenses: 1400, nonEssential: 0 },
    ];
    const base = cumulativeBalance(months, ZERO_SIM);
    const cut = cumulativeBalance(months, { ...ZERO_SIM, cutWantsPct: 50 });
    expect(base).toEqual([1450, 4250, 7350]);
    // Corte de 50%: +375, +150, +0
    expect(cut.map((v, i) => v - base[i])).toEqual([375, 525, 525]);
  });
});
