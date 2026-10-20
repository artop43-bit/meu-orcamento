import { describe, expect, it } from "vitest";

import { groupEntry, groupOf, LEAVES, leafLabel, neighborLeaf, parentOf } from "./navigation";

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
    expect(neighborLeaf("/orcamento", 1)).toBe("/contas");
    expect(neighborLeaf("/divisoes", 1)).toBe("/calendario");
    expect(neighborLeaf("/orcamento", -1)).toBeNull();
    expect(neighborLeaf("/historico", 1)).toBeNull();
    expect(neighborLeaf("/ajustes/perfil", 1)).toBeNull();
  });

  it("voltar das sub-telas", () => {
    expect(parentOf("/ajustes/perfil")).toBe("/ajustes");
    expect(parentOf("/ajustes/solicitacoes/123")).toBe("/ajustes/solicitacoes");
    expect(parentOf("/dividas/abc/tabela")).toBe("/dividas");
    expect(parentOf("/ajustes")).toBeNull();
    expect(parentOf("/orcamento/2030-01")).toBeNull();
  });
});
