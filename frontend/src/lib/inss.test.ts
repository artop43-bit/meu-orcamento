import { describe, expect, it } from "vitest";

import { inssDiscount } from "./inss";

describe("inssDiscount (tabela 2026)", () => {
  it("salário mínimo paga 7,5%", () => {
    expect(inssDiscount(1621)).toMatchObject({ inss: 121.58, net: 1499.42 });
  });

  it("faixas progressivas", () => {
    // 1621 × 7,5% + (2902,84 − 1621) × 9% + (3000 − 2902,84) × 12%
    expect(inssDiscount(3000).inss).toBe(248.6);
    expect(inssDiscount(5000).inss).toBe(501.51);
  });

  it("acima do teto, o desconto fica no máximo", () => {
    expect(inssDiscount(8475.55).inss).toBe(988.09);
    expect(inssDiscount(15000)).toMatchObject({ inss: 988.09, net: 14011.91 });
  });

  it("sem salário, sem desconto", () => {
    expect(inssDiscount(0)).toEqual({ gross: 0, inss: 0, net: 0, rate: 0 });
  });
});
