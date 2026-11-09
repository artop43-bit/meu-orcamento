import { describe, expect, it } from "vitest";

import { chartsFor, colorFor, compactValue, formatValue, niceScale, niceStep } from "./format";

describe("formatValue", () => {
  it("dinheiro, porcentagem e vazio", () => {
    expect(formatValue(1234.5, "money")).toMatch(/1\.234,50/);
    expect(formatValue(12.34, "percent")).toBe("12,3%");
    expect(formatValue(null, "money")).toBe("—");
  });
});

describe("compactValue", () => {
  it("encurta para eixos", () => {
    expect(compactValue(2300, "money")).toBe("R$ 2,3 mil");
    expect(compactValue(850.4, "money")).toBe("R$ 850");
    expect(compactValue(-1500, "money")).toBe("-R$ 1,5 mil");
    expect(compactValue(1_250_000, "money")).toBe("R$ 1,3 mi");
    expect(compactValue(18.6, "percent")).toBe("19%");
  });
});

describe("chartsFor", () => {
  it("categorias aceitam ranking e rosca; meses aceitam linhas e área", () => {
    expect(chartsFor("category", 1)).toContain("donut");
    expect(chartsFor("month", 1)).not.toContain("donut");
    expect(chartsFor("month_category", 4)[0]).toBe("stacked");
  });
});

describe("colorFor", () => {
  it("usa a cor própria ou a paleta", () => {
    expect(colorFor("#123456", 3)).toBe("#123456");
    // v1.6: a 1ª série segue a cor de destaque; as demais são tokens do tema.
    expect(colorFor(null, 0)).toBe("var(--accent)");
    expect(colorFor(null, 1)).toBe("var(--chart-1)");
  });
});

describe("niceScale", () => {
  it("passos redondos que cobrem o maior valor", () => {
    const s = niceScale(0, 4300);
    expect(s.ticks).toEqual([0, 2000, 4000, 6000]);
    expect(s.max).toBeGreaterThanOrEqual(4300);
  });
  it("inclui valores negativos e o zero", () => {
    const s = niceScale(-1172, 900);
    expect(s.min).toBeLessThanOrEqual(-1172);
    expect(s.ticks).toContain(0);
    expect(s.ticks.every((t, i, all) => i === 0 || t > all[i - 1])).toBe(true);
  });
  it("sem dados não quebra", () => {
    expect(niceScale(0, 0).ticks).toEqual([0, 1]);
  });
  it("porcentagens pequenas", () => {
    expect(niceScale(-24, 27).ticks).toEqual([-40, -20, 0, 20, 40]);
  });
});

describe("niceStep", () => {
  it("arredonda para 1, 2, 2,5, 5 ou 10", () => {
    expect(niceStep(1075)).toBe(2000);
    expect(niceStep(240)).toBe(250);
    expect(niceStep(0)).toBe(1);
  });
});
