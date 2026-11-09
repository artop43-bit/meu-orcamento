/**
 * Tema do Meu Orçamento (v1.1): todas as cores do app saem destes tokens.
 *
 * Um tema é um conjunto completo de tokens para o modo claro e o escuro (Theme). Uma cor de
 * destaque troca só os tokens de destaque (AccentTheme). O arquivo src/theme.css é GERADO a
 * partir daqui (`npm run theme`); um teste garante que os dois nunca divergem e que todas as
 * combinações de texto e fundo passam no contraste WCAG AA.
 *
 * Temas personalizados (futuro): basta montar um Theme com estes tokens.
 */

export const TOKENS = [
  "bg",
  "surface",
  "surface-2",
  "fg",
  "muted",
  "subtle",
  "border",
  "border-strong",
  "accent",
  "accent-hover",
  "accent-soft",
  "accent-fg",
  "ok",
  "ok-bg",
  "error",
  "error-bg",
  "warn",
  "warn-bg",
  "info",
  "info-bg",
  "expense",
  "shadow-sm",
  "shadow",
  "shadow-lg",
] as const;

export type Token = (typeof TOKENS)[number];
export type Palette = Record<Token, string>;
export type Theme = { light: Palette; dark: Palette };

export const ACCENT_TOKENS = ["accent", "accent-hover", "accent-soft", "accent-fg"] as const;
export type AccentPalette = Record<(typeof ACCENT_TOKENS)[number], string>;
export type AccentTheme = { label: string; light: AccentPalette; dark: AccentPalette };

export const BASE: Theme = {
  light: {
    bg: "#f4f5f3",
    surface: "#ffffff",
    "surface-2": "#f8f9f7",
    fg: "#17201c",
    muted: "#5f6b66",
    subtle: "#66706b",
    border: "#e2e6e3",
    "border-strong": "#cfd6d2",
    accent: "#1f7a62",
    "accent-hover": "#186650",
    "accent-soft": "#e3f2ec",
    "accent-fg": "#ffffff",
    ok: "#1b7a4b",
    "ok-bg": "#e6f4ec",
    error: "#b42318",
    "error-bg": "#fdecea",
    warn: "#a15c07",
    "warn-bg": "#fdf3e2",
    info: "#24548f",
    "info-bg": "#eaf1fb",
    expense: "#d97b29",
    "shadow-sm": "0 1px 2px rgb(16 24 20 / 6%)",
    shadow: "0 1px 3px rgb(16 24 20 / 6%), 0 4px 12px rgb(16 24 20 / 5%)",
    "shadow-lg": "0 12px 40px rgb(16 24 20 / 18%)",
  },
  dark: {
    // v1.6: escuro mais profundo, para o brilho da cor de destaque aparecer (estilo Padrão).
    bg: "#080c0a",
    surface: "#0f1613",
    "surface-2": "#151e1a",
    fg: "#e8ece9",
    muted: "#9ba5a0",
    subtle: "#8b958f",
    border: "#1f2a25",
    "border-strong": "#2e3a35",
    accent: "#3fb994",
    "accent-hover": "#55c9a5",
    "accent-soft": "#173229",
    "accent-fg": "#07150f",
    ok: "#4cc38a",
    "ok-bg": "#15281d",
    error: "#f97066",
    "error-bg": "#2d1715",
    warn: "#e8b04b",
    "warn-bg": "#2b2213",
    info: "#84b4ef",
    "info-bg": "#16212e",
    expense: "#e9934a",
    "shadow-sm": "0 1px 2px rgb(0 0 0 / 30%)",
    shadow: "0 1px 3px rgb(0 0 0 / 30%), 0 6px 16px rgb(0 0 0 / 25%)",
    "shadow-lg": "0 16px 48px rgb(0 0 0 / 55%)",
  },
};

/**
 * "Positivo" (saldo que sobra, "Paga", metas, gráficos de sobra, mensagens de sucesso) segue a
 * cor de destaque, para a tela não misturar o verde fixo com a cor escolhida. Nas cores quentes,
 * que se confundiriam com alerta (rosa, vermelho, laranja e âmbar), o positivo fica neutro; o vermelho continua
 * só para o negativo. Cotações de mercado mantêm verde/vermelho (convenção da bolsa: --ok/--error).
 */
export const NEUTRAL_POSITIVE = ["rosa", "vermelho", "laranja", "ambar"] as const;

/**
 * Cores das séries de gráfico (v1.6). A 1ª série é sempre a cor de destaque; estas vêm depois.
 * Uma versão para o claro (mais escura) e outra para o escuro (mais clara): todas passam no
 * contraste de 3:1 para elementos gráficos sobre o fundo e os cartões, em todos os estilos.
 */
export const CHART = {
  light: ["#c2621a", "#3b6ea8", "#8e5b9a", "#c4433f", "#2f8580", "#9a7410", "#8a6448", "#76706c"],
  dark: ["#e8833a", "#6f9fd8", "#c08fd0", "#ee6b66", "#6cc3bd", "#e2c050", "#c49a7a", "#aaa39e"],
} as const;

/** Cores de destaque (a primeira é a padrão). A ordem é a do seletor em Preferências. */
export const ACCENTS = {
  verde: {
    label: "Verde",
    light: { accent: "#1f7a62", "accent-hover": "#186650", "accent-soft": "#e3f2ec", "accent-fg": "#ffffff" },
    dark: { accent: "#3fb994", "accent-hover": "#55c9a5", "accent-soft": "#173229", "accent-fg": "#07150f" },
  },
  azul: {
    label: "Azul",
    light: { accent: "#1d5fbf", "accent-hover": "#184f9f", "accent-soft": "#e4edfa", "accent-fg": "#ffffff" },
    dark: { accent: "#6aa6f0", "accent-hover": "#86b8f4", "accent-soft": "#16243a", "accent-fg": "#0b0f14" },
  },
  indigo: {
    label: "Índigo",
    light: { accent: "#4338ca", "accent-hover": "#3730a3", "accent-soft": "#eceafd", "accent-fg": "#ffffff" },
    dark: { accent: "#a29cf8", "accent-hover": "#b6b1fa", "accent-soft": "#221f45", "accent-fg": "#0d0b24" },
  },
  roxo: {
    label: "Roxo",
    light: { accent: "#6a3fb5", "accent-hover": "#5a33a0", "accent-soft": "#efe8fa", "accent-fg": "#ffffff" },
    dark: { accent: "#b392f0", "accent-hover": "#c4a9f4", "accent-soft": "#2a2140", "accent-fg": "#0b0f14" },
  },
  rosa: {
    label: "Rosa",
    light: { accent: "#b3285f", "accent-hover": "#982150", "accent-soft": "#fbe8f0", "accent-fg": "#ffffff" },
    dark: { accent: "#f27aa9", "accent-hover": "#f596bb", "accent-soft": "#3a1a28", "accent-fg": "#1f0a13" },
  },
  vermelho: {
    label: "Vermelho",
    light: { accent: "#b8322a", "accent-hover": "#9c2a23", "accent-soft": "#fdebea", "accent-fg": "#ffffff" },
    dark: { accent: "#f47a6f", "accent-hover": "#f6948b", "accent-soft": "#3a1a17", "accent-fg": "#1f0907" },
  },
  laranja: {
    label: "Laranja",
    light: { accent: "#a8500a", "accent-hover": "#8f4408", "accent-soft": "#fbeadb", "accent-fg": "#ffffff" },
    dark: { accent: "#f0a35c", "accent-hover": "#f4b47a", "accent-soft": "#33230f", "accent-fg": "#0b0f14" },
  },
  ambar: {
    label: "Âmbar",
    light: { accent: "#8f5600", "accent-hover": "#774700", "accent-soft": "#fdf1dc", "accent-fg": "#ffffff" },
    dark: { accent: "#f0b44c", "accent-hover": "#f4c46e", "accent-soft": "#33260f", "accent-fg": "#1c1303" },
  },
  ciano: {
    label: "Ciano",
    light: { accent: "#0b6e80", "accent-hover": "#095b6a", "accent-soft": "#e0f3f6", "accent-fg": "#ffffff" },
    dark: { accent: "#4cc4d8", "accent-hover": "#6dd0e0", "accent-soft": "#123036", "accent-fg": "#04161a" },
  },
  grafite: {
    label: "Grafite",
    light: { accent: "#3f4a45", "accent-hover": "#2f3833", "accent-soft": "#eceeed", "accent-fg": "#ffffff" },
    dark: { accent: "#c3cbc7", "accent-hover": "#d5dbd8", "accent-soft": "#2a302d", "accent-fg": "#121614" },
  },
} satisfies Record<string, AccentTheme>;

export type AccentName = keyof typeof ACCENTS;
