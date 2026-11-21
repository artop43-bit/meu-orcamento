import { describe, expect, it } from "vitest";

import { expiryBadgeInfo, formatVaultSize, parseInlineMarkdown } from "./memory";

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
});
