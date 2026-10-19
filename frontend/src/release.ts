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
  { title: "Navegação reorganizada.", text: "Configurações reunidas em Ajustes; novas telas de Contas, Busca e Para revisar." },
  { title: "Formulário de despesa em etapas.", text: "Valor total ou por parcela junto do campo, atalhos de parcelas e resumo em tempo real." },
  { title: "Datas no padrão dd/mm/aaaa.", text: "Em todo o app, com validação de datas inválidas." },
  { title: "Categoria automática ampliada.", text: "Mais de mil termos reconhecidos e novas categorias: Compras, Assinaturas e Pets." },
  { title: "Contas e saldos.", text: "Saldo por conta, previsão para o fim do mês e transferências." },
  { title: "Disponível hoje com simulação.", text: "Veja o impacto de uma despesa antes de realizá-la." },
];

export function releaseLabel(): string {
  const date = new Date(RELEASE.releasedAt);
  const day = date.toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo" });
  const time = date.toLocaleTimeString("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit" });
  return `Versão ${RELEASE.version} · ${day} às ${time}`;
}
