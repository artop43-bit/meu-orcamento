import { describe, expect, it } from "vitest";

import {
  buildNoteBacklinks,
  expiryBadgeInfo,
  extractWikilinks,
  foldMemoryText,
  formatVaultSize,
  noteMatchesQuery,
  parseInlineMarkdown,
} from "./memory";

describe("helpers de Memória Documental (Cofre e Caderno)", () => {
  it("traduz status de validade e tamanho de arquivo em português", () => {
    expect(expiryBadgeInfo("expired", -4)).toEqual({ label: "Vencido há 4d", tone: "warn" });
    expect(expiryBadgeInfo("expiring_soon", 12)).toEqual({ label: "Vence em 12d", tone: "warn" });
    expect(expiryBadgeInfo("valid", 180)).toEqual({ label: "Válido (180d)", tone: "accent" });
    expect(expiryBadgeInfo("no_expiry", null)).toEqual({ label: "Permanente", tone: "neutral" });

    expect(formatVaultSize(48 * 1024)).toBe("48 KB");
    expect(formatVaultSize(2.5 * 1024 * 1024)).toBe("2,5 MB");
  });

  it("extrai [[wikilinks]], negrito e código de linhas Markdown sem HTML", () => {
    const segs = parseInlineMarkdown("Conferir **contrato** em [[Ata Comercial|alias]] e `POP-01`.");
    expect(segs).toEqual([
      { kind: "text", text: "Conferir " },
      { kind: "bold", text: "contrato" },
      { kind: "text", text: " em " },
      { kind: "wikilink", label: "Ata Comercial" },
      { kind: "text", text: " e " },
      { kind: "code", text: "POP-01" },
      { kind: "text", text: "." },
    ]);
  });

  it("extrai links [[...]] únicos e preserva ordem ignorando duplicatas por acento", () => {
    const links = extractWikilinks(
      "Consultar [[Roteiro Comercial]], [[roteiro comercial|atalho]] e [[Orçamento Padrão]].",
    );
    expect(links).toEqual(["Roteiro Comercial", "Orçamento Padrão"]);
    expect(extractWikilinks("Sem colchetes [simples] ou [[ ]]")).toEqual([]);
  });

  it("monta backlinks bidirecionais mesmo com diferenças de acento e maiúsculas", () => {
    const notes = [
      { id: "1", title: "Orçamento Padrão", content: "Base principal" },
      { id: "2", title: "Ata de Reunião", content: "Seguir [[orcamento padrao|modelo]]." },
      { id: "3", title: "POP Atendimento", content: "Revisar [[Orçamento Padrão]] antes de enviar." },
      { id: "4", title: "Nota Avulsa", content: "Sem referência." },
    ];
    expect(buildNoteBacklinks(notes, "1")).toEqual([
      { id: "2", title: "Ata de Reunião" },
      { id: "3", title: "POP Atendimento" },
    ]);
    expect(buildNoteBacklinks(notes, "999")).toEqual([]);
  });

  it("normaliza acentos e encontra notas em buscas com cedilha ou til", () => {
    expect(foldMemoryText("  Atenção · Orçamento  NFe  ")).toBe("atencao · orcamento nfe");
    const nota = {
      title: "Garantia · Instalação Elétrica",
      folder: "Operação",
      tags: ["Revisão", "Técnica"],
      excerpt: "Condição válida até março para manutenção preventiva.",
    };
    expect(noteMatchesQuery(nota, "instalacao eletrica")).toBe(true);
    expect(noteMatchesQuery(nota, "MANUTENCAO")).toBe(true);
    expect(noteMatchesQuery(nota, "revisao")).toBe(true);
    expect(noteMatchesQuery(nota, "operacao")).toBe(true);
    expect(noteMatchesQuery(nota, "inexistente")).toBe(false);
  });
});
