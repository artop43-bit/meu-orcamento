import { describe, expect, it } from "vitest";

import {
  filterReleasesBySolution,
  RELEASE_SOLUTIONS,
  RELEASES,
  releaseSolutionLabel,
  releaseDate,
  releaseKey,
} from "./releases";
import {
  LEGACY_SEEN_KEY,
  markWhatsNewSeen,
  releaseDateLabel,
  releaseLabel,
  releaseOf,
  releaseSolutionForPath,
  releaseTag,
  shouldShowWhatsNew,
  whatsNewSeenKey,
} from "../release";

describe("notas da versão separadas por solução", () => {
  it("cobre o Hub de Soluções e todas as soluções integradas", () => {
    expect(RELEASE_SOLUTIONS.map((s) => s.id)).toEqual([
      "hub",
      "meu-orcamento",
      "mensageria",
      "dashboard-crm",
      "catalogo",
      "propostas",
      "projetos",
      "agenda",
      "cofre",
      "caderno",
    ]);
    expect(releaseSolutionLabel("hub")).toBe("Hub de Soluções");
    expect(releaseSolutionLabel("mensageria")).toBe("Mensageria");
    expect(releaseSolutionLabel("dashboard-crm")).toBe("Dashboard & CRM");
    expect(releaseSolutionLabel(undefined)).toBe("Meu Orçamento");
  });

  it("filtra as notas da versão exclusivamente pela solução escolhida", () => {
    const all = filterReleasesBySolution(RELEASES, "all");
    expect(all.length).toBe(RELEASES.length);

    for (const sol of RELEASE_SOLUTIONS) {
      const items = filterReleasesBySolution(RELEASES, sol.id);
      expect(items.length).toBeGreaterThan(0);
      for (const item of items) {
        expect(item.solution ?? "meu-orcamento").toBe(sol.id);
      }
    }
  });

  it("mantém versões próprias em preparação sem inventar uma data de publicação", () => {
    const versions = {
      hub: "1.0.0",
      "meu-orcamento": "1.11.0",
      mensageria: "1.0.0",
      "dashboard-crm": "1.0.0",
      catalogo: "1.0.0",
      propostas: "1.0.0",
      projetos: "1.0.0",
      agenda: "1.0.0",
      cofre: "1.0.0",
      caderno: "1.0.0",
    };
    const keys = new Set<string>();
    for (const { id } of RELEASE_SOLUTIONS) {
      const release = releaseOf(id);
      const first = filterReleasesBySolution(RELEASES, id)[0];
      expect(release.version).toBe(versions[id]);
      expect(first.version).toBe(release.version);
      expect(release.releasedAt).toBeNull();
      expect(releaseDate(first)).toBe("Em preparação");
      expect(releaseLabel(id)).toBe(`Versão ${release.version} · Em preparação`);
      keys.add(releaseKey(first));
    }
    expect(keys.size).toBe(10);
    expect(releaseDateLabel("2026-11-18T00:20:00Z")).toBe("17/11/2026 às 21:20");
  });

  it("preserva a 1.10.0 publicada com horário e correção do cartão, sem o bot novo", () => {
    const published = filterReleasesBySolution(RELEASES, "meu-orcamento").find((r) => r.version === "1.10.0")!;
    expect(published.title).toBe("Leitor de cupons novo");
    expect(published.date).toBe("17/11/2026 às 21:20");
    expect(published.sections.map((s) => s.title)).toEqual(["Ler comprovante (foto)", "Correções"]);
    expect(published.sections[0].items).toHaveLength(4);
    expect(published.sections[1].items).toContain("Cartão de crédito: a compra nunca entra como paga e sempre ocupa o limite do cartão.");
    expect(JSON.stringify(published)).not.toMatch(/bot|CRM|Mensageria/);
  });

  it("informa a solução da tela em relatórios dentro do limite aceito pela API", () => {
    for (const [path, id] of [
      ["/", "hub"],
      ["/perfil", "hub"],
      ["/entrar", "hub"],
      ["/orcamento", "meu-orcamento"],
      ["/mensageria", "mensageria"],
      ["/crm/funil", "dashboard-crm"],
      ["/catalogo", "catalogo"],
      ["/propostas", "propostas"],
      ["/projetos", "projetos"],
      ["/agenda", "agenda"],
      ["/cofre", "cofre"],
      ["/caderno", "caderno"],
    ] as const) {
      expect(releaseSolutionForPath(path)).toBe(id);
      expect(releaseTag(id).length).toBeLessThanOrEqual(20);
    }
  });

  it("mostra Novidades uma vez por solução e versão, preservando a chave antiga", () => {
    const values = new Map<string, string>([[LEGACY_SEEN_KEY, "1.10.0"]]);
    const storage = { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => { values.set(key, value); } };
    expect(shouldShowWhatsNew("meu-orcamento", storage)).toBe(true);
    markWhatsNewSeen("meu-orcamento", storage);
    expect(shouldShowWhatsNew("meu-orcamento", storage)).toBe(false);
    expect(shouldShowWhatsNew("mensageria", storage)).toBe(true);
    markWhatsNewSeen("mensageria", storage);
    expect(shouldShowWhatsNew("mensageria", storage)).toBe(false);
    expect(shouldShowWhatsNew("hub", storage)).toBe(true);
    expect(values.get(LEGACY_SEEN_KEY)).toBe("1.10.0");
    values.set(whatsNewSeenKey("mensageria"), "0.9.0");
    expect(shouldShowWhatsNew("mensageria", storage)).toBe(true);
  });

  it("marca a versão atual para conta nova e migra a versão já vista do orçamento", () => {
    const values = new Map<string, string>();
    const storage = { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => { values.set(key, value); } };
    expect(shouldShowWhatsNew("hub", storage)).toBe(false);
    expect(values.get(whatsNewSeenKey("hub"))).toBe("1.0.0");
    values.set(LEGACY_SEEN_KEY, releaseOf("meu-orcamento").version);
    expect(shouldShowWhatsNew("meu-orcamento", storage)).toBe(false);
    expect(values.get(whatsNewSeenKey("meu-orcamento"))).toBe("1.11.0");
  });
});
