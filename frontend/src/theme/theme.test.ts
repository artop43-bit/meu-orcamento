import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { themeCss } from "./css.ts";
import { ACCENTS, BASE, TOKENS, type AccentPalette, type Palette } from "./tokens.ts";

const read = (path: string) => readFileSync(new URL(path, import.meta.url), "utf-8").replace(/\r\n/g, "\n");

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const lin = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * lin(r!) + 0.7152 * lin(g!) + 0.0722 * lin(b!);
}

/** Contraste WCAG entre duas cores (1 a 21). */
export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi! + 0.05) / (lo! + 0.05);
}

const AA = 4.5;

describe("tema", () => {
  it("src/theme.css está em dia com os tokens (rode `npm run theme` depois de mudar cores)", () => {
    expect(read("../theme.css")).toBe(themeCss());
  });

  it("claro e escuro definem todos os tokens", () => {
    for (const palette of [BASE.light, BASE.dark]) expect(Object.keys(palette).sort()).toEqual([...TOKENS].sort());
  });

  it("textos do tema base passam no contraste AA", () => {
    for (const p of [BASE.light, BASE.dark] as Palette[]) {
      for (const bg of [p.bg, p.surface, p["surface-2"]]) {
        expect(contrast(p.fg, bg)).toBeGreaterThanOrEqual(AA);
        expect(contrast(p.muted, bg)).toBeGreaterThanOrEqual(AA);
      }
      for (const [fg, bg] of [
        [p.ok, p["ok-bg"]],
        [p.error, p["error-bg"]],
        [p.warn, p["warn-bg"]],
        [p.info, p["info-bg"]],
      ] as const) {
        expect(contrast(fg, bg)).toBeGreaterThanOrEqual(AA);
      }
    }
  });

  it.each(Object.entries(ACCENTS))("cor de destaque %s passa no contraste AA (claro e escuro)", (_, accent) => {
    const pairs: [AccentPalette, Palette][] = [
      [accent.light, BASE.light],
      [accent.dark, BASE.dark],
    ];
    for (const [a, base] of pairs) {
      // Texto e ícones no destaque sobre os fundos; texto do botão sobre o destaque; chip ativo.
      expect(contrast(a.accent, base.surface)).toBeGreaterThanOrEqual(AA);
      expect(contrast(a.accent, base.bg)).toBeGreaterThanOrEqual(AA);
      expect(contrast(a["accent-fg"], a.accent)).toBeGreaterThanOrEqual(AA);
      expect(contrast(a["accent-fg"], a["accent-hover"])).toBeGreaterThanOrEqual(AA);
      expect(contrast(a.accent, a["accent-soft"])).toBeGreaterThanOrEqual(AA);
    }
  });

  it("styles.css não usa cores fixas fora dos tokens (salvo as exceções listadas)", () => {
    const css = read("../styles.css")
      // Impressão sempre em preto e branco, por definição.
      .replace(/@media print \{[\s\S]*?\n\}\n/g, "");
    // Exceções conscientes: branco e preto puros (texto sobre fotos, sombras), o QR code do 2FA
    // (precisa de fundo branco para ser lido) e o degradê do logotipo.
    const allowed = new Set(["#fff", "#ffffff", "#000", "#000000"]);
    const found = [...css.matchAll(/#[0-9a-fA-F]{3,8}\b/g)].map((m) => m[0].toLowerCase()).filter((hex) => !allowed.has(hex));
    expect(found).toEqual([]);
  });
});
