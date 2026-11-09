import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { themeCss } from "./css.ts";
import { STYLES } from "./styles.ts";
import { ACCENTS, BASE, CHART, TOKENS, type AccentPalette, type Palette } from "./tokens.ts";

const read = (path: string) => readFileSync(new URL(path, import.meta.url), "utf-8").replace(/\r\n/g, "\n");

type Rgba = [number, number, number, number];

/** Lê "#rrggbb" ou "rgba(r, g, b, a)". */
function parse(color: string): Rgba {
  if (color.startsWith("#")) return [1, 3, 5].map((i) => parseInt(color.slice(i, i + 2), 16)).concat(1) as Rgba;
  const [r, g, b, a = 1] = color.match(/[\d.]+/g)!.map(Number);
  return [r!, g!, b!, a];
}

const hex = ([r, g, b]: Rgba) => `#${[r, g, b].map((v) => Math.round(v).toString(16).padStart(2, "0")).join("")}`;

/** Cor que a pessoa vê: `top` (com transparência) pintada sobre `bottom` (opaca). */
export function over(top: string, bottom: string): string {
  const [r, g, b, a] = parse(top);
  const [r2, g2, b2] = parse(bottom);
  return hex([r * a + r2 * (1 - a), g * a + g2 * (1 - a), b * a + b2 * (1 - a), 1]);
}

/** color-mix(in srgb, a pct%, b) entre duas cores opacas. */
const mix = (a: string, pct: number, b: string) => over(`rgba(${parse(a).slice(0, 3).join(", ")}, ${pct / 100})`, b);

function luminance(color: string): number {
  const [r, g, b] = parse(color).slice(0, 3).map((v) => v / 255);
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
    // v1.6: a camada dos estilos visuais (visual.css) segue a mesma regra.
    const css = (read("../styles.css") + read("../visual.css"))
      // Impressão sempre em preto e branco, por definição.
      .replace(/@media print \{[\s\S]*?\n\}\n/g, "");
    // Exceções conscientes: branco e preto puros (texto sobre fotos, sombras), o QR code do 2FA
    // (precisa de fundo branco para ser lido) e o degradê do logotipo.
    const allowed = new Set(["#fff", "#ffffff", "#000", "#000000"]);
    const found = [...css.matchAll(/#[0-9a-fA-F]{3,8}\b/g)].map((m) => m[0].toLowerCase()).filter((hex) => !allowed.has(hex));
    expect(found).toEqual([]);
  });

  // v1.6: cada estilo, no claro e no escuro, com cada cor de destaque. O fundo testado é o pior
  // caso: o ponto mais forte do brilho (cor de destaque misturada ao fundo); os cartões são a
  // superfície (com transparência) pintada sobre esse fundo, e a segunda superfície sobre o cartão.
  const combos = Object.entries(STYLES).flatMap(([style, def]) =>
    Object.entries(ACCENTS).flatMap(([accentName, accent]) =>
      (["light", "dark"] as const).map((mode) => [`${style} · ${accentName} · ${mode === "light" ? "claro" : "escuro"}`, def[mode], accent[mode], BASE[mode]] as const),
    ),
  );

  it.each(combos)("estilo %s: textos e destaque legíveis sobre o fundo e os cartões", (_, styleMode, accent, base) => {
    const p = { ...base, ...accent, ...styleMode.overrides } as Palette;
    const backgrounds = [p.bg, mix(p.accent, styleMode.glow, p.bg), mix(p["accent-hover"], styleMode.glow, p.bg)];
    for (const page of backgrounds) {
      const card = over(p.surface, page);
      const inner = over(p["surface-2"], card);
      for (const bg of [page, card, inner, styleMode.solid]) {
        expect(contrast(p.fg, bg), `texto sobre ${bg}`).toBeGreaterThanOrEqual(AA);
        expect(contrast(p.muted, bg), `texto secundário sobre ${bg}`).toBeGreaterThanOrEqual(AA);
        expect(contrast(p.accent, bg), `destaque sobre ${bg}`).toBeGreaterThanOrEqual(AA);
      }
    }
    expect(contrast(p["accent-fg"], p.accent)).toBeGreaterThanOrEqual(AA);
  });

  // Gráficos: cada série (a 1ª é a cor de destaque) com 3:1 sobre o fundo e os cartões.
  it.each(combos)("estilo %s: séries de gráfico visíveis", (name, styleMode, accent, base) => {
    const p = { ...base, ...accent, ...styleMode.overrides } as Palette;
    const series = [p.accent, ...(name.endsWith("claro") ? CHART.light : CHART.dark)];
    const backgrounds = [p.bg, mix(p.accent, styleMode.glow, p.bg), mix(p["accent-hover"], styleMode.glow, p.bg)];
    for (const page of backgrounds) {
      for (const bg of [page, over(p.surface, page), styleMode.solid]) {
        for (const color of series) expect(contrast(color, bg), `${color} sobre ${bg}`).toBeGreaterThanOrEqual(3);
      }
    }
  });

  // Telas com texto branco sobre a cor de destaque escurecida (Retrospectiva, imagem para
  // compartilhar e a lateral do login): o ponto mais claro do degradê é 55% da cor com preto.
  it.each(Object.entries(ACCENTS))("texto branco sobre o degradê da cor %s", (_, accent) => {
    for (const a of [accent.light.accent, accent.dark.accent]) {
      expect(contrast("#ffffff", mix(a, 55, "#000000"))).toBeGreaterThanOrEqual(AA);
    }
  });

  // No Liquid glass as superfícies são translúcidas: como cor de TEXTO, use --surface-solid ou
  // --accent-fg (opacos e testados), nunca --surface/--surface-2.
  it("nenhum texto pintado com a cor translúcida das superfícies", () => {
    const css = read("../styles.css") + read("../visual.css");
    expect(css.match(/(?<![-\w])color:\s*var\(--surface(-2)?\)/g)).toBeNull();
  });
});
