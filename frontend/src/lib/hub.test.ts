import { describe, expect, it } from "vitest";

import { activeSolutions, defaultSolutionRoute, findSolution, HUB_SOLUTIONS } from "./hub";

describe("catálogo do hub de soluções", () => {
  it("expõe o Meu Orçamento como solução ativa principal", () => {
    const main = findSolution("meu-orcamento");
    expect(main?.status).toBe("active");
    expect(main?.to).toBe("/orcamento");
    expect(defaultSolutionRoute()).toBe("/orcamento");
  });

  it("separa soluções ativas das prévias em preparação", () => {
    const active = activeSolutions();
    expect(active.length).toBeGreaterThanOrEqual(1);
    expect(active.every((item) => item.status === "active" && item.to !== null)).toBe(true);
    expect(HUB_SOLUTIONS.some((item) => item.status === "soon")).toBe(true);
  });

  it("mantém identificadores únicos para suportar futuras integrações", () => {
    const ids = HUB_SOLUTIONS.map((item) => item.id);
    expect(new Set(ids).size).toBe(ids.length);
  });
});
