/**
 * Estilos visuais (v1.6): a FORMA do app — fundo, transparência, desfoque, cantos e brilho.
 *
 * Um estilo combina com qualquer tema (claro/escuro) e qualquer cor de destaque: ele só troca
 * alguns tokens de superfície e acrescenta o "brilho" do fundo, calculado a partir da cor de
 * destaque escolhida. As cores de texto e de destaque continuam vindo de tokens.ts.
 *
 * Este arquivo gera parte de src/theme.css (`npm run theme`) e é a fonte dos testes de
 * contraste: cada estilo é testado com cada cor de destaque, no claro e no escuro, sobre o pior
 * fundo possível (o ponto mais forte do brilho). Estilo novo no futuro = uma entrada aqui, mais
 * as regras de forma dele em src/visual.css.
 */
import type { Palette } from "./tokens.ts";

export type StyleMode = {
  /** Tokens de cor trocados neste estilo (aceitam transparência, rgba). */
  overrides: Partial<Palette>;
  /** Fundo opaco para o que flutua sobre o conteúdo (menus, janelas, dicas de gráfico). */
  solid: string;
  /** Força do brilho do fundo: % da cor de destaque misturada ao fundo no ponto mais forte. */
  glow: number;
};

export type VisualStyle = { label: string; text: string; light: StyleMode; dark: StyleMode };

export const STYLES = {
  padrao: {
    label: "Padrão",
    text: "Grade sutil ao fundo, cartões foscos e brilho na cor de destaque.",
    light: { overrides: {}, solid: "#ffffff", glow: 0 },
    dark: { overrides: {}, solid: "#111915", glow: 0 },
  },
  glass: {
    label: "Liquid glass",
    text: "Vidro translúcido com reflexos e a cor de destaque desfocada ao fundo.",
    light: {
      overrides: {
        bg: "#f9fbfa",
        surface: "rgba(255, 255, 255, 0.66)",
        "surface-2": "rgba(255, 255, 255, 0.5)",
        border: "rgba(23, 32, 28, 0.1)",
        "border-strong": "rgba(23, 32, 28, 0.2)",
        muted: "#4f5a55",
        subtle: "#55605b",
      },
      solid: "#fbfcfc",
      glow: 7,
    },
    dark: {
      overrides: {
        bg: "#05080a",
        surface: "rgba(16, 22, 20, 0.62)",
        "surface-2": "rgba(255, 255, 255, 0.07)",
        border: "rgba(255, 255, 255, 0.13)",
        "border-strong": "rgba(255, 255, 255, 0.22)",
        fg: "#f2f6f4",
        muted: "#b2bcb7",
        subtle: "#a3aea9",
      },
      solid: "#121a17",
      glow: 25,
    },
  },
} satisfies Record<string, VisualStyle>;

export type StyleName = keyof typeof STYLES;

export const DEFAULT_STYLE: StyleName = "padrao";

export const isStyleName = (value: unknown): value is StyleName => typeof value === "string" && value in STYLES;
