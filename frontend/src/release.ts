/**
 * Versão do app, exibida no fim do menu. Atualizar a cada update, junto com o arquivo
 * do changelog (pasta changelog/), que tem a mesma versão, data e hora.
 */
export const RELEASE = {
  version: "1.0.0",
  // Data e hora (Brasília) em que o update foi publicado.
  releasedAt: "2026-10-20T20:00:00-03:00",
};

/** Mostrado uma vez em "Novidades" depois do update (curto: o detalhe fica no changelog). */
export const RELEASE_NOTES: { title: string; text: string }[] = [
  { title: "Dívidas e patrimônio.", text: "Financiamentos com parcelas no Orçamento, saldo devedor, tabela e patrimônio líquido mês a mês." },
  { title: "Mês financeiro e alertas.", text: "O mês pode começar no dia do salário; alertas avisam gastos fora do padrão e assinaturas mais caras." },
  { title: "Divisões.", text: "Divida despesas e acompanhe quem deve a quem." },
  { title: "App Android.", text: "Baixe em Ajustes › App e notificações e receba avisos no celular." },
];

export function releaseLabel(): string {
  const date = new Date(RELEASE.releasedAt);
  const day = date.toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo" });
  const time = date.toLocaleTimeString("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit" });
  return `Versão ${RELEASE.version} · ${day} às ${time}`;
}
