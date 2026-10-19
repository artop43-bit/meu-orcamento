/**
 * Versão do app, exibida no fim do menu. Atualizar a cada update, junto com o arquivo
 * do changelog (pasta changelog/), que tem a mesma versão, data e hora.
 */
export const RELEASE = {
  version: "0.7.6",
  // Data e hora (Brasília) em que o update foi publicado.
  releasedAt: "2026-10-19T19:00:00-03:00",
};

/** Mostrado uma vez em "Novidades" depois do update (curto: o detalhe fica no changelog). */
export const RELEASE_NOTES: { title: string; text: string }[] = [
  { title: "Foto e banner no celular.", text: "Correção: a prévia e o recorte da imagem não abriam no celular. Agora funcionam em todos os navegadores." },
  { title: "Minhas solicitações.", text: "Sugestões e problemas viram conversas com a administração, com imagens e aviso de resposta nova (Ajustes)." },
  { title: "Perfil.", text: "Foto, banner, resumo pessoal e retrospectiva do mês ou do ano (Ajustes › Perfil)." },
];

export function releaseLabel(): string {
  const date = new Date(RELEASE.releasedAt);
  const day = date.toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo" });
  const time = date.toLocaleTimeString("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit" });
  return `Versão ${RELEASE.version} · ${day} às ${time}`;
}
