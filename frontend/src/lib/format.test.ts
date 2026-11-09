import { describe, expect, it } from "vitest";

import { addMonths, money, moneyInput, monthLabel, parseMoney, percent, shortDate, textOn } from "./format";

// O Intl usa espaço não separável entre "R$" e o número.
const brl = (text: string) => text.replace(/ /g, " ");

describe("money", () => {
  it("formata em reais", () => {
    expect(brl(money("1234.5"))).toBe("R$ 1.234,50");
    expect(brl(money(0))).toBe("R$ 0,00");
    expect(brl(money(null))).toBe("R$ 0,00");
  });

  it("mostra negativos", () => {
    expect(brl(money("-12.3"))).toBe("-R$ 12,30");
  });
});

describe("parseMoney", () => {
  it.each([
    ["1.234,56", "1234.56"],
    ["1234,5", "1234.50"],
    ["1234.56", "1234.56"],
    ["R$ 30", "30.00"],
    ["  2.300,00 ", "2300.00"],
    ["0,99", "0.99"],
  ])("%s -> %s", (input, expected) => {
    expect(parseMoney(input)).toBe(expected);
  });

  it.each(["", "abc", "1,2,3", "-10", "12,345"])("recusa %j", (input) => {
    expect(parseMoney(input)).toBeNull();
  });
});

describe("moneyInput", () => {
  it("usa vírgula decimal para edição", () => {
    expect(moneyInput("1500.00")).toBe("1500,00");
    expect(moneyInput("39.9")).toBe("39,90");
  });
});

describe("meses", () => {
  it("nomeia meses", () => {
    expect(monthLabel("2026-10")).toBe("Outubro de 2026");
    expect(monthLabel("2026-03", true)).toBe("Mar/26");
  });

  it("soma e subtrai meses atravessando o ano", () => {
    expect(addMonths("2026-12", 1)).toBe("2027-01");
    expect(addMonths("2026-01", -1)).toBe("2025-12");
    expect(addMonths("2026-10", 15)).toBe("2028-01");
    expect(addMonths("2026-10", 0)).toBe("2026-10");
  });
});

describe("shortDate e percent", () => {
  it("formata datas curtas", () => {
    expect(shortDate("2026-10-05")).toBe("05/10");
    expect(shortDate(null)).toBe("");
  });

  it("formata percentuais", () => {
    expect(percent(16.6)).toBe("16,6%");
    expect(percent(null)).toBe("—");
  });
});

describe("mês financeiro", () => {
  it("rótulo do período e mês atual com início no dia 5", async () => {
    const { cycleLabel, setCycleStart, thisMonth } = await import("./format");
    setCycleStart(5);
    expect(cycleLabel("2030-10")).toBe("5/10 a 4/11");
    expect(cycleLabel("2031-01")).toBe("5/1 a 4/2");
    setCycleStart(1);
    expect(cycleLabel("2030-10")).toBe("");
    expect(thisMonth()).toMatch(/^\d{4}-\d{2}$/);
  });
});

describe("textOn (v1.6)", () => {
  it("escolhe branco em cores escuras e quase preto em cores claras", () => {
    expect(textOn("#8a05be")).toBe("#ffffff");
    expect(textOn("#17201c")).toBe("#ffffff");
    expect(textOn("#f0b44c")).toBe("#0b0f0d");
    expect(textOn("#ffffff")).toBe("#0b0f0d");
  });

  it("sem cor válida, segue a cor do texto do tema", () => {
    expect(textOn(null)).toBe("var(--fg)");
    expect(textOn("azul")).toBe("var(--fg)");
  });
});
