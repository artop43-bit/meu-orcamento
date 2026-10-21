import { describe, expect, it } from "vitest";

import { rebalance } from "./rebalance";

describe("meta de alocação", () => {
  it("aporte vai para a classe abaixo do alvo", () => {
    // Hoje: 8.000 em renda fixa e 2.000 em ações; meta 60/40; aporte de 2.000 → total 12.000.
    const rows = rebalance({ renda_fixa: 8000, acoes: 2000 }, { renda_fixa: 60, acoes: 40 }, 2000);
    const add = Object.fromEntries(rows.map((r) => [r.kind, r.add]));
    expect(add).toEqual({ renda_fixa: 0, acoes: 2000 });
  });

  it("quando o aporte cobre a diferença, o resto segue a meta", () => {
    const rows = rebalance({ renda_fixa: 6000, acoes: 3000 }, { renda_fixa: 60, acoes: 40 }, 3000);
    // Total 12.000: alvo 7.200 / 4.800 → faltam 1.200 e 1.800 (= 3.000).
    const add = Object.fromEntries(rows.map((r) => [r.kind, r.add]));
    expect(add).toEqual({ renda_fixa: 1200, acoes: 1800 });
    const more = Object.fromEntries(rebalance({ renda_fixa: 6000, acoes: 4000 }, { renda_fixa: 60, acoes: 40 }, 5000).map((r) => [r.kind, r.add]));
    // Total 15.000: alvo 9.000 / 6.000 → faltam 3.000 e 2.000.
    expect(more).toEqual({ renda_fixa: 3000, acoes: 2000 });
  });

  it("classe fora da meta não recebe aporte", () => {
    const rows = rebalance({ renda_fixa: 1000, cripto: 500 }, { renda_fixa: 100 }, 500);
    expect(rows.find((r) => r.kind === "cripto")!.add).toBe(0);
  });
});
