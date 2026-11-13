/**
 * Versão do app, exibida no fim do menu. Atualizar a cada update, junto com o arquivo
 * do changelog (pasta changelog/), que tem a mesma versão, data e hora.
 */
export const RELEASE = {
  version: "1.8.0",
  // Data e hora (Brasília) em que o update foi publicado.
  releasedAt: "2026-11-13T23:00:00-03:00",
};

/** Mostrado uma vez em "Novidades" depois do update (curto: o detalhe fica no changelog). */
export const RELEASE_NOTES: { title: string; text: string }[] = [
  {
    title: "Empréstimos com juros nas Divisões.",
    text: "Empreste com juros e parcelas (por dia, semana, 15 dias ou mês): a taxa sai do lucro que você quer, e cada parcela entra no Orçamento como receita prevista.",
  },
  { title: "Divisões em linhas.", text: "Uma linha por pessoa, que abre e fecha, com busca por nome e filtros." },
];

export function releaseLabel(): string {
  const date = new Date(RELEASE.releasedAt);
  const day = date.toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo" });
  const time = date.toLocaleTimeString("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit" });
  return `Versão ${RELEASE.version} · ${day} às ${time}`;
}
