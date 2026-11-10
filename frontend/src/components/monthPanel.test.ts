import { describe, expect, it } from "vitest";

import type { MonthData } from "../api/budget";
import { cycleRange, greeting, monthStops } from "./monthPanel";

const base = {
  month: "2026-11",
  summary: { balance: "-285.41" },
  incomes: [{ id: "i1", description: "Salário", amount: "3000", day: 15 }],
  expenses: [
    { id: "e1", description: "Aluguel", amount: "1400", due_date: "2026-11-10", paid: false },
    { id: "e2", description: "Internet", amount: "100", due_date: "2026-11-12", paid: false },
    { id: "e3", description: "Padaria", amount: "20", due_date: "2026-11-03", paid: true },
    { id: "e4", description: "Luz", amount: "150", due_date: "2026-11-05", paid: false },
    { id: "e5", description: "Celular", amount: "60", due_date: "2026-11-28", paid: false },
  ],
} as unknown as MonthData;

describe("painel do Orçamento (v1.7.5)", () => {
  const range = cycleRange("2026-11", 1);

  it("o mês financeiro respeita o dia de início", () => {
    expect(range.map((d) => d.getDate())).toEqual([1, 30]);
    const custom = cycleRange("2026-11", 5);
    expect([custom[0].getMonth() + 1, custom[0].getDate(), custom[1].getMonth() + 1, custom[1].getDate()]).toEqual([11, 5, 12, 4]);
  });

  it("a saudação resume o que importa agora", () => {
    const out = greeting(base, "2026-11-10", 15, "Arthur", range);
    expect(out.hello).toBe("Boa tarde, Arthur");
    expect(out.parts[0]).toContain("no negativo");
    expect(out.parts[1]).toBe("1 conta(s) em atraso.");
    expect(out.parts[2]).toContain("2 contas vencem nos próximos 7 dias");
    expect(greeting(base, "2026-11-10", 8, null, range).hello).toBe("Bom dia");
    const empty = { ...base, incomes: [], expenses: [], summary: { balance: "0" } } as unknown as MonthData;
    expect(greeting(empty, "2026-11-10", 20, null, range).parts).toEqual(["Comece lançando as receitas e as despesas do mês."]);
  });

  it("a linha do mês agrupa o que cai perto e marca atrasadas, a vencer e pagas", () => {
    const stops = monthStops(base, "2026-11-10", range);
    expect(stops.map((s) => s.pos)).toEqual([...stops.map((s) => s.pos)].sort((a, b) => a - b));
    const kinds = Object.fromEntries(stops.map((s) => [s.label, s.kind]));
    expect(kinds["Salário"]).toBe("income");
    expect(kinds["Celular"]).toBe("next");
    // Padaria (dia 3, paga) e Luz (dia 5, atrasada) ficam juntas, e vale a situação mais grave.
    const early = stops.find((s) => s.count === 2 && s.pos < 20);
    expect(early?.kind).toBe("late");
    expect(early?.amount).toBe(170);
    // Nunca passa do limite de paradas.
    expect(monthStops(base, "2026-11-10", range, 8, 3).length).toBeLessThanOrEqual(3);
  });
});
