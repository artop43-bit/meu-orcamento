import { STYLES, type StyleMode } from "./styles.ts";
import { ACCENTS, BASE, CHART, NEUTRAL_POSITIVE, TOKENS, type AccentPalette, type Palette } from "./tokens.ts";

const HEADER = `/* =====================================================================
   ARQUIVO GERADO por src/theme/tokens.ts (npm run theme). Não edite aqui.
   Tokens de cor do tema claro e escuro e as cores de destaque.
   ===================================================================== */
`;

function block(selector: string, values: Partial<Palette> | AccentPalette | Record<string, string>, indent = "", extra = ""): string {
  const lines = Object.entries(values).map(([token, value]) => `${indent}  --${token}: ${value};`);
  return `${indent}${selector} {\n${lines.join("\n")}${extra ? `\n${indent}${extra}` : ""}\n${indent}}\n`;
}

/** O CSS completo do tema (o que vai em src/theme.css). */
export function themeCss(): string {
  const light = Object.fromEntries(TOKENS.map((t) => [t, BASE.light[t]])) as Palette;
  const dark = Object.fromEntries(TOKENS.map((t) => [t, BASE.dark[t]])) as Palette;
  const parts = [HEADER];
  parts.push(block(":root", light, "", "  color-scheme: light dark;"));
  // Escuro: pelo sistema (se a pessoa não escolheu "Claro") ou escolhido na conta.
  parts.push(`@media (prefers-color-scheme: dark) {\n${block(':root:not([data-theme="light"])', dark, "  ")}}\n`);
  parts.push(block(':root[data-theme="dark"]', dark, "", "  color-scheme: dark;"));
  parts.push(':root[data-theme="light"] {\n  color-scheme: light;\n}\n');
  // Positivo: segue a cor de destaque (neutro nas cores quentes; ver NEUTRAL_POSITIVE).
  parts.push(":root {\n  --positive: var(--accent);\n  --positive-bg: var(--accent-soft);\n  --positive-fg: var(--accent-fg);\n}\n");
  const neutral = NEUTRAL_POSITIVE.map((name) => `:root[data-accent="${name}"]`).join(",\n");
  parts.push(`${neutral} {\n  --positive: var(--fg);\n  --positive-bg: var(--surface-2);\n  --positive-fg: var(--surface-solid);\n}\n`);
  // Séries de gráfico (v1.6): claro e escuro.
  const chartVars = (colors: readonly string[]) => Object.fromEntries(colors.map((c, i) => [`chart-${i + 1}`, c]));
  parts.push(block(":root", chartVars(CHART.light)));
  parts.push(`@media (prefers-color-scheme: dark) {\n${block(':root:not([data-theme="light"])', chartVars(CHART.dark), "  ")}}\n`);
  parts.push(block(':root[data-theme="dark"]', chartVars(CHART.dark)));
  for (const [name, accent] of Object.entries(ACCENTS)) {
    if (name === "verde") continue; // é o padrão do tema base
    parts.push(`/* ${accent.label} */\n`);
    parts.push(block(`:root[data-accent="${name}"]`, accent.light));
    parts.push(`@media (prefers-color-scheme: dark) {\n${block(`:root:not([data-theme="light"])[data-accent="${name}"]`, accent.dark, "  ")}}\n`);
    parts.push(block(`:root[data-theme="dark"][data-accent="${name}"]`, accent.dark));
  }
  parts.push(stylesCss());
  return parts.join("\n");
}

/** Variáveis de um estilo num modo: tokens trocados, fundo opaco e brilho do fundo. */
function styleVars(mode: StyleMode): Record<string, string> {
  return {
    ...mode.overrides,
    "surface-solid": mode.solid,
    glow: `color-mix(in srgb, var(--accent) ${mode.glow}%, transparent)`,
    "glow-2": `color-mix(in srgb, var(--accent-hover) ${mode.glow}%, transparent)`,
  } as Record<string, string>;
}

/** Estilos visuais (v1.6): o Padrão é o tema base; os demais trocam tokens por cima dele. */
function stylesCss(): string {
  const parts = ["/* Estilos visuais (src/theme/styles.ts) */\n"];
  parts.push(block(":root", styleVars(STYLES.padrao.light)));
  parts.push(`@media (prefers-color-scheme: dark) {\n${block(':root:not([data-theme="light"])', styleVars(STYLES.padrao.dark), "  ")}}\n`);
  parts.push(block(':root[data-theme="dark"]', styleVars(STYLES.padrao.dark)));
  for (const [name, style] of Object.entries(STYLES)) {
    if (name === "padrao") continue;
    parts.push(`/* ${style.label} */\n`);
    parts.push(block(`:root[data-style="${name}"]`, styleVars(style.light)));
    parts.push(`@media (prefers-color-scheme: dark) {\n${block(`:root:not([data-theme="light"])[data-style="${name}"]`, styleVars(style.dark), "  ")}}\n`);
    parts.push(block(`:root[data-theme="dark"][data-style="${name}"]`, styleVars(style.dark)));
  }
  return parts.join("\n");
}
