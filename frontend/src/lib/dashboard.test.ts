import { describe, expect, it } from "vitest";

import { DEFAULT_DASHBOARD, move, readDashboard } from "./dashboard";

describe("painel do Orçamento", () => {
  it("sem nada salvo, mostra tudo na ordem padrão", () => {
    expect(readDashboard(null)).toEqual(DEFAULT_DASHBOARD);
    expect(readDashboard("não é json")).toEqual(DEFAULT_DASHBOARD);
  });

  it("mantém a ordem salva e acrescenta cartões novos no fim", () => {
    const list = readDashboard(JSON.stringify([{ key: "daily", visible: true }, { key: "kpis", visible: false }, { key: "x", visible: true }]));
    expect(list.slice(0, 2)).toEqual([
      { key: "daily", visible: true },
      { key: "kpis", visible: false },
    ]);
    expect(list).toHaveLength(DEFAULT_DASHBOARD.length);
  });

  it("move só dentro da mesma área", () => {
    const moved = move(DEFAULT_DASHBOARD, "daily", -1);
    const side = moved.filter((c) => ["alerts", "daily", "goal", "incomes", "breakdown"].includes(c.key)).map((c) => c.key);
    expect(side.slice(0, 2)).toEqual(["daily", "alerts"]);
    // O primeiro da área não sobe mais.
    expect(move(DEFAULT_DASHBOARD, "quick", -1)).toEqual(DEFAULT_DASHBOARD);
  });
});
