import { describe, expect, it } from "vitest";

import {
  AGENDA_ALL_LAYERS,
  buildMonthGrid,
  calcProjectProfitability,
  formatAgendaPeriod,
  formatIsoDateBr,
  groupTimelineByDay,
  monthBoundsIso,
  shiftIsoDate,
  startOfWeekIso,
} from "./work";

describe("helpers de projetos e agenda unificada", () => {
  it("encurta o período da agenda e distingue meses e anos", () => {
    expect(formatAgendaPeriod("2026-11-15", "2026-11-21")).toBe("15–21 nov");
    expect(formatAgendaPeriod("2026-11-08", "2026-11-08")).toBe("8 nov");
    expect(formatAgendaPeriod("2026-10-29", "2026-11-04")).toBe("29 out – 4 nov");
    expect(formatAgendaPeriod("2026-12-29", "2027-01-04")).toBe("29 dez 2026 – 4 jan 2027");
  });

  it("calcula margem líquida e ganho real por hora do projeto", () => {
    expect(calcProjectProfitability(2000, 500, 5)).toEqual({
      netMargin: 1500,
      effectiveHourly: 300,
    });
    expect(calcProjectProfitability(1200, 400, 0)).toEqual({
      netMargin: 800,
      effectiveHourly: 0,
    });
  });

  it("calcula intervalos de semana, grade mensal de 42 dias e agrupamento por data", () => {
    expect(startOfWeekIso("2026-11-20")).toBe("2026-11-15");
    expect(shiftIsoDate("2026-11-30", 2)).toBe("2026-12-02");
    expect(monthBoundsIso("2026-02-10")).toEqual({
      start: "2026-02-01",
      end: "2026-02-28",
    });
    const grid = buildMonthGrid("2026-11-20");
    expect(grid.days).toHaveLength(42);
    expect(formatIsoDateBr("2026-11-20")).toBe("20/11/2026");

    const grouped = groupTimelineByDay([
      {
        uid: "a1",
        id: "1",
        layer: "agenda",
        kind: "meeting",
        title: "Reunião 1",
        subtitle: null,
        date: "2026-11-20",
        time: "10:00",
        status: "scheduled",
      },
      {
        uid: "c1",
        id: "2",
        layer: "crm",
        kind: "deal_close",
        title: "Fechamento",
        subtitle: null,
        date: "2026-11-20",
        time: null,
        status: "open",
      },
    ]);
    expect(grouped).toHaveLength(1);
    expect(grouped[0]!.items).toHaveLength(2);
    expect(AGENDA_ALL_LAYERS).toEqual(["agenda", "messaging", "crm", "projects", "budget", "cofre"]);
  });
});
