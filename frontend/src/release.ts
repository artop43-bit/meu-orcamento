/**
 * Versão do app, exibida no fim do menu. Atualizar a cada update, junto com o arquivo
 * do changelog (pasta changelog/), que tem a mesma versão, data e hora.
 */
export const RELEASE = {
  version: "0.8.0",
  // Data e hora (Brasília) em que o update foi publicado.
  releasedAt: "2026-10-20T02:30:00-03:00",
};

/** Mostrado uma vez em "Novidades" depois do update (curto: o detalhe fica no changelog). */
export const RELEASE_NOTES: { title: string; text: string }[] = [
  { title: "Avisos por e-mail.", text: "Lembrete das contas a vencer, resumo do mês e aviso de acesso por aparelho novo. Ajuste em Preferências." },
  { title: "Metas com objetivo.", text: "Tipo, imagem, motivação e projeção de conclusão, com a meta principal em destaque no Orçamento." },
  { title: "Importar e exportar.", text: "Uma só importação para OFX, CSV, Excel e backup, com prévia e desfazer; exportação com filtros e resumo anual." },
  { title: "Comprovantes.", text: "Anexe a foto do recibo ou da nota fiscal na despesa." },
];

export function releaseLabel(): string {
  const date = new Date(RELEASE.releasedAt);
  const day = date.toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo" });
  const time = date.toLocaleTimeString("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit" });
  return `Versão ${RELEASE.version} · ${day} às ${time}`;
}
