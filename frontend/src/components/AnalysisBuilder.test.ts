import { describe, expect, it } from "vitest";

import type { Category } from "../api/budget";
import { DEFAULT_CONFIG, describe as describeConfig, normalize, PRESETS } from "./AnalysisBuilder";

const categories: Category[] = [
  { id: "c1", name: "Lazer", is_essential: false, color: "#b07aa1", monthly_limit: null },
  { id: "c2", name: "Moradia", is_essential: true, color: "#4e79a7", monthly_limit: null },
];

describe("normalize", () => {
  it("renda, sobra e poupança só por mês, sem filtro de categoria", () => {
    const c = normalize({ ...DEFAULT_CONFIG, metric: "income", group: "category", categories: ["c1"], chart: "donut" });
    expect(c.group).toBe("month");
    expect(c.categories).toEqual([]);
    expect(c.chart).toBe("bar");
  });

  it("patrimônio é por tipo e sem comparação", () => {
    const c = normalize({ ...DEFAULT_CONFIG, metric: "investments", compare: "last_year" });
    expect(c.group).toBe("kind");
    expect(c.compare).toBe("none");
    expect(["hbar", "donut", "bar", "table"]).toContain(c.chart);
  });

  it("agrupamento por mês × categoria usa barras empilhadas no lugar da rosca", () => {
    expect(normalize({ ...DEFAULT_CONFIG, group: "month_category", chart: "donut" }).chart).toBe("stacked");
  });

  it("período personalizado ganha início e fim; preset limpa as datas", () => {
    const custom = normalize({ ...DEFAULT_CONFIG, period: "custom" });
    expect(custom.start).toMatch(/^\d{4}-\d{2}$/);
    expect(custom.end).toMatch(/^\d{4}-\d{2}$/);
    expect(normalize({ ...custom, period: "12m" }).start).toBeNull();
  });

  it("todas as sugestões prontas já são combinações válidas", () => {
    for (const preset of PRESETS) expect(normalize(preset.config)).toEqual({ ...preset.config, start: null, end: null });
  });
});

describe("describe", () => {
  it("monta um título legível com as categorias filtradas", () => {
    const title = describeConfig({ ...DEFAULT_CONFIG, categories: ["c1"], period: "12m" }, categories);
    expect(title).toBe("Gastos (Lazer) por mês · últimos 12 meses");
  });

  it("patrimônio é sempre 'hoje'", () => {
    expect(describeConfig(normalize({ ...DEFAULT_CONFIG, metric: "investments" }), categories)).toBe("Patrimônio por tipo · hoje");
  });
});
