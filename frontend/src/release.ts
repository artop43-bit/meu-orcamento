/**
 * Versão do app, exibida no fim do menu. Atualizar a cada update, junto com o arquivo
 * do changelog (pasta changelog/), que tem a mesma versão, data e hora.
 */
export const RELEASE = {
  version: "1.7.6.1",
  // Data e hora (Brasília) em que o update foi publicado.
  releasedAt: "2026-11-12T11:45:00-03:00",
};

/** Mostrado uma vez em "Novidades" depois do update (curto: o detalhe fica no changelog). */
export const RELEASE_NOTES: { title: string; text: string }[] = [
  { title: "Exportar em PDF.", text: "O recorte que você escolher (período, contas e categorias) sai também em PDF, pronto para ler ou enviar." },
  { title: "Tela de exportar mais simples.", text: "Filtros em listas com busca, resumo do recorte na hora e os formatos lado a lado." },
];

export function releaseLabel(): string {
  const date = new Date(RELEASE.releasedAt);
  const day = date.toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo" });
  const time = date.toLocaleTimeString("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit" });
  return `Versão ${RELEASE.version} · ${day} às ${time}`;
}
