import { describe, expect, it } from "vitest";

import { comparePlans, simulate, type PayoffDebt } from "./payoff";

const DEBTS: PayoffDebt[] = [
  { id: "cartao", name: "Rotativo", balance: 2000, rate: 0.08, kind: "fixed", payment: 200 },
  { id: "pessoal", name: "Empréstimo pessoal", balance: 6000, rate: 0.03, kind: "price", remaining: 24 },
  { id: "loja", name: "Crediário", balance: 500, rate: 0.02, kind: "fixed", payment: 100 },
];

describe("plano de quitação", () => {
  it("só as parcelas: Price quita no prazo", () => {
    const result = simulate([DEBTS[1]!], 0, "minimum");
    expect(result.months).toBe(24);
    // 24 parcelas de ~354,28 sobre 6.000 → ~2.502,79 de juros.
    expect(result.interest).toBeCloseTo(2502.79, 0);
  });

  it("juros mais altos primeiro paga menos juros; menor dívida primeiro quita a menor antes", () => {
    const plans = comparePlans(DEBTS, 300);
    expect(plans.avalanche.interest).toBeLessThan(plans.snowball.interest);
    expect(plans.snowball.interest).toBeLessThan(plans.minimum.interest);
    expect(plans.snowball.finished[0]!.id).toBe("loja");
    expect(plans.avalanche.finished[0]!.id).toBe("cartao");
    expect(plans.avalanche.months!).toBeLessThan(plans.minimum.months!);
  });

  it("parcela que não cobre os juros nunca termina", () => {
    const result = simulate([{ id: "x", name: "X", balance: 1000, rate: 0.1, kind: "fixed", payment: 50 }], 0, "minimum");
    expect(result.months).toBeNull();
  });

  it("SAC: parcela cai e a dívida termina no prazo", () => {
    const result = simulate([{ id: "casa", name: "Casa", balance: 12000, rate: 0.01, kind: "sac", remaining: 12 }], 0, "minimum");
    expect(result.months).toBe(12);
    // Juros SAC: 1% sobre 12.000, 11.000, ..., 1.000 = 780.
    expect(result.interest).toBeCloseTo(780, 0);
  });
});
