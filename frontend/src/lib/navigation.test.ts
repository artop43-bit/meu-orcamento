import { describe, expect, it } from "vitest";

import { groupEntry, groupOf, LEAVES, leafLabel, neighborTab, parentOf } from "./navigation";

describe("navegação em grupos", () => {
  it("encontra o grupo de cada tela", () => {
    expect(groupOf("/cartoes")?.key).toBe("carteira");
    expect(groupOf("/orcamento/2030-01")?.key).toBe("orcamento");
    expect(groupOf("/analises")?.label).toBe("Análises");
    expect(groupOf("/ajustes")).toBeUndefined();
    expect(groupEntry(groupOf("/metas")!)).toBe("/calendario");
  });

  it("títulos das telas", () => {
    expect(leafLabel("/analises")).toBe("Insights");
    expect(leafLabel("/investimentos")).toBe("Investimentos");
    expect(leafLabel("/ajustes")).toBeUndefined();
  });

  it("deslizar anda pelas telas na ordem do menu", () => {
    expect(LEAVES[0]).toBe("/orcamento");
    // Deslizar troca as abas de baixo, não os submenus.
    expect(neighborTab("/orcamento", 1)).toBe("carteira");
    expect(neighborTab("/orcamento/2026-10", 1)).toBe("carteira");
    expect(neighborTab("/contas", 1)).toBe("planejamento");
    expect(neighborTab("/divisoes", -1)).toBe("orcamento");
    expect(neighborTab("/metas", 1)).toBe("analises");
    expect(neighborTab("/orcamento", -1)).toBeNull();
    expect(neighborTab("/historico", 1)).toBeNull();
    // Telas do "Mais" e sub-telas não trocam de aba.
    expect(neighborTab("/investimentos", 1)).toBeNull();
    expect(neighborTab("/investimentos", -1)).toBeNull();
    expect(neighborTab("/ajustes/perfil", 1)).toBeNull();
    expect(neighborTab("/dividas/abc", 1)).toBeNull();
  });

  it("voltar das sub-telas", () => {
    expect(parentOf("/ajustes/perfil")).toBe("/ajustes");
    expect(parentOf("/mensagens/conversas/123")).toBe("/mensagens/conversas");
    expect(parentOf("/mensagens/conversas")).toBe("/mensagens");
    expect(parentOf("/mensagens")).toBeNull();
    expect(parentOf("/dividas/abc/tabela")).toBe("/dividas");
    expect(parentOf("/ajustes")).toBeNull();
    expect(parentOf("/orcamento/2030-01")).toBeNull();
  });
});
