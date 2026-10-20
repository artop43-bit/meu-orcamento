/**
 * Estrutura do menu (v1.1): poucos itens no topo, com grupos que se abrem no próprio menu.
 * Também define a ordem das telas para o gesto de deslizar no celular e para onde "voltar"
 * leva a partir de uma sub-tela.
 */

export type NavLeaf = { to: string; label: string };
export type NavGroup = { key: string; label: string; to?: string; children?: NavLeaf[] };

export const GROUPS: NavGroup[] = [
  { key: "orcamento", label: "Orçamento", to: "/orcamento" },
  {
    key: "carteira",
    label: "Carteira",
    children: [
      { to: "/contas", label: "Contas" },
      { to: "/cartoes", label: "Cartões" },
      { to: "/dividas", label: "Dívidas" },
      { to: "/divisoes", label: "Divisões" },
    ],
  },
  {
    key: "planejamento",
    label: "Planejamento",
    children: [
      { to: "/calendario", label: "Calendário" },
      { to: "/metas", label: "Metas" },
    ],
  },
  { key: "investimentos", label: "Investimentos", to: "/investimentos" },
  {
    key: "analises",
    label: "Análises",
    children: [
      { to: "/analises", label: "Insights" },
      { to: "/historico", label: "Histórico" },
    ],
  },
];

/** Grupos que viram abas embaixo no celular (Investimentos fica no "Mais"). */
export const MOBILE_TABS = ["orcamento", "carteira", "planejamento", "analises"];

/** Telas na ordem do menu: o gesto de deslizar anda por elas. */
export const LEAVES: string[] = GROUPS.flatMap((g) => (g.children ? g.children.map((c) => c.to) : [g.to!]));

/** Seção da URL ("/contas/abc" → "/contas"). */
export function sectionOf(pathname: string): string {
  return "/" + (pathname.split("/")[1] ?? "");
}

export function groupOf(pathname: string): NavGroup | undefined {
  const section = sectionOf(pathname);
  return GROUPS.find((g) => g.to === section || g.children?.some((c) => c.to === section));
}

export function groupEntry(group: NavGroup): string {
  return group.to ?? group.children![0]!.to;
}

/** Título da tela atual (barra do topo no celular e título da aba do navegador). */
export function leafLabel(pathname: string): string | undefined {
  const section = sectionOf(pathname);
  for (const g of GROUPS) {
    if (g.to === section) return g.label;
    const child = g.children?.find((c) => c.to === section);
    if (child) return child.label;
  }
  return undefined;
}

/**
 * Para onde "voltar" leva a partir de uma sub-tela (deslizar para a direita no celular).
 * Telas do menu e meses do orçamento/calendário não são sub-telas.
 */
export function parentOf(pathname: string): string | null {
  const parts = pathname.split("/").filter(Boolean);
  if (parts[0] === "ajustes" && parts.length >= 2) {
    return parts[1] === "solicitacoes" && parts.length >= 3 ? "/ajustes/solicitacoes" : "/ajustes";
  }
  if (parts[0] === "dividas" && parts.length >= 2) return "/dividas";
  if (parts[0] === "relatorio") return "/ajustes/dados?aba=exportar";
  if (["revisar", "busca", "mensagens", "admin"].includes(parts[0] ?? "")) return null;
  return null;
}

/** Tela vizinha na ordem do menu (1 = próxima, -1 = anterior). */
export function neighborLeaf(pathname: string, dir: 1 | -1): string | null {
  const index = LEAVES.indexOf(sectionOf(pathname));
  if (index < 0) return null;
  return LEAVES[index + dir] ?? null;
}
