/**
 * Versão do app, exibida no fim do menu. Atualizar a cada update, junto com o arquivo
 * do changelog (pasta changelog/), que tem a mesma versão, data e hora.
 */
export const RELEASE = {
  version: "0.6.0",
  // Data e hora (Brasília) em que o update foi publicado.
  releasedAt: "2026-10-19T09:00:00-03:00",
};

/** Mostrado uma vez em "Novidades" depois do update (curto: o detalhe fica no changelog). */
export const RELEASE_NOTES: { title: string; text: string }[] = [
  { title: "Lançar numa frase.", text: "Ctrl+K (ou o campo rápido do Orçamento): \"mercado 120 pix ontem\"." },
  { title: "Cartões de crédito.", text: "A compra cai na fatura certa; veja limite, faturas e o melhor dia de compra." },
  { title: "Quanto posso gastar hoje.", text: "E o saldo previsto dia a dia, com aviso antes de ficar no negativo." },
  { title: "Ações em lote.", text: "Selecione várias contas para pagar, mudar categoria ou excluir; \"pagar vencidas\"." },
  { title: "Regras e assinaturas.", text: "\"Sempre usar esta categoria\" e a lista de assinaturas com o custo por ano." },
  { title: "Do seu jeito.", text: "Esconder valores (tecla P), tema, cor, tamanho do texto e modo compacto em Preferências." },
  { title: "Fale com a gente.", text: "\"Enviar sugestão\" no menu manda ideias e problemas direto para quem faz o app." },
];

export function releaseLabel(): string {
  const date = new Date(RELEASE.releasedAt);
  const day = date.toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo" });
  const time = date.toLocaleTimeString("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit" });
  return `Versão ${RELEASE.version} · ${day} às ${time}`;
}
