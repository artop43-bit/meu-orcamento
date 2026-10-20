import { describe, expect, it } from "vitest";

import { cashOrInstallments, compound, emergencyFund, prepay, savingPlan, toMonthly } from "./calculators";

describe("calculadoras", () => {
  it("converte taxa anual em mensal por juros compostos", () => {
    expect(toMonthly(12, "yearly")).toBeCloseTo(0.009489, 6);
    expect(toMonthly(1, "monthly")).toBe(0.01);
  });

  it("juros compostos com aporte mensal", () => {
    // 1.000 inicial + 100/mês a 1% a.m. por 12 meses = 1.126,83 + 1.268,25
    const r = compound(1000, 100, 1, "monthly", 12);
    expect(r.final).toBeCloseTo(2395.08, 2);
    expect(r.invested).toBe(2200);
    expect(r.interest).toBeCloseTo(195.08, 2);
    expect(r.points).toHaveLength(12);
  });

  it("quanto guardar por mês para chegar a um valor", () => {
    expect(savingPlan(12000, 0, 0, "monthly", 12).monthly).toBe(1000);
    const r = savingPlan(10000, 2000, 1, "monthly", 24);
    // Confere: aplicando o resultado, chega ao alvo.
    expect(compound(2000, r.monthly, 1, "monthly", 24).final).toBeCloseTo(10000, 0);
    expect(savingPlan(1000, 5000, 1, "monthly", 12).monthly).toBe(0);
  });

  it("à vista ou parcelado", () => {
    // Sem rendimento, qualquer desconto favorece o à vista.
    expect(cashOrInstallments(1200, 5, 12, 0, "monthly").better).toBe("cash");
    // Rendimento alto e desconto pequeno: parcelar sem juros sai melhor.
    const r = cashOrInstallments(1200, 1, 12, 1, "monthly");
    expect(r.better).toBe("installments");
    expect(r.breakEvenDiscount).toBeGreaterThan(5);
  });

  it("antecipar parcelas ou aplicar", () => {
    const r = prepay(500, 6, 3, 1, "monthly");
    expect(r.better).toBe("prepay");
    expect(r.discount).toBeGreaterThan(0);
    expect(prepay(500, 6, 0.5, 1, "monthly").better).toBe("invest");
  });

  it("reserva de emergência", () => {
    expect(emergencyFund(3000, 6, 6000)).toEqual({ target: 18000, missing: 12000, coverage: 2 });
  });
});
