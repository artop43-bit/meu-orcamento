/**
 * Versão do app, exibida no fim do menu. Atualizar a cada update, junto com o arquivo
 * do changelog (pasta changelog/), que tem a mesma versão, data e hora.
 */
export const RELEASE = {
  version: "1.4.0",
  // Data e hora (Brasília) em que o update foi publicado.
  releasedAt: "2026-10-21T17:00:00-03:00",
};

/** Mostrado uma vez em "Novidades" depois do update (curto: o detalhe fica no changelog). */
export const RELEASE_NOTES: { title: string; text: string }[] = [
  { title: "Cobre via Pix.", text: "Cadastre sua chave em Preferências e cobre quem te deve nas Divisões." },
  { title: "Vale-refeição, MEI e IR.", text: "Novo tipo de conta, faturamento do MEI e o resumo do Imposto de Renda no relatório anual." },
  { title: "Raio-x dos gastos.", text: "Tarifas e juros do ano, sua inflação e projetos para agrupar despesas." },
];

export function releaseLabel(): string {
  const date = new Date(RELEASE.releasedAt);
  const day = date.toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo" });
  const time = date.toLocaleTimeString("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit" });
  return `Versão ${RELEASE.version} · ${day} às ${time}`;
}
