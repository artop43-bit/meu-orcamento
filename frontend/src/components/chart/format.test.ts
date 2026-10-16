import { describe, expect, it } from "vitest";

import { chartsFor, colorFor, compactValue, formatValue } from "./format";

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
    expect(colorFor(null, 0)).toMatch(/^#/);
  });
});
