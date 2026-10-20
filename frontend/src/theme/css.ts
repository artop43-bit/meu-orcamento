import { ACCENTS, BASE, TOKENS, type AccentPalette, type Palette } from "./tokens.ts";

const HEADER = `/* =====================================================================
   ARQUIVO GERADO por src/theme/tokens.ts (npm run theme). Não edite aqui.
   Tokens de cor do tema claro e escuro e as cores de destaque.
   ===================================================================== */
`;

function block(selector: string, values: Partial<Palette> | AccentPalette, indent = "", extra = ""): string {
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
  for (const [name, accent] of Object.entries(ACCENTS)) {
    if (name === "verde") continue; // é o padrão do tema base
    parts.push(`/* ${accent.label} */\n`);
    parts.push(block(`:root[data-accent="${name}"]`, accent.light));
    parts.push(`@media (prefers-color-scheme: dark) {\n${block(`:root:not([data-theme="light"])[data-accent="${name}"]`, accent.dark, "  ")}}\n`);
    parts.push(block(`:root[data-theme="dark"][data-accent="${name}"]`, accent.dark));
  }
  return parts.join("\n");
}
