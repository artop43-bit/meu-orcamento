/**
 * Versão do app, exibida no fim do menu. Atualizar a cada update, junto com o arquivo
 * do changelog (pasta changelog/), que tem a mesma versão, data e hora.
 */
export const RELEASE = {
  version: "0.7.5",
  // Data e hora (Brasília) em que o update foi publicado.
  releasedAt: "2026-10-19T17:45:00-03:00",
};

/** Mostrado uma vez em "Novidades" depois do update (curto: o detalhe fica no changelog). */
export const RELEASE_NOTES: { title: string; text: string }[] = [
  { title: "Minhas solicitações.", text: "Sugestões e problemas viram conversas com a administração, com imagens e aviso de resposta nova (Ajustes)." },
  { title: "Perfil.", text: "Foto, banner, resumo pessoal e retrospectiva do mês ou do ano para baixar e compartilhar (Ajustes › Perfil)." },
  { title: "Cartão de débito.", text: "Compras no débito saem na hora da conta vinculada, sem usar limite nem fatura." },
  { title: "Formulários revisados.", text: "Campos alinhados, datas com mensagens claras e nada é salvo com data ou dia inválido." },
];

export function releaseLabel(): string {
  const date = new Date(RELEASE.releasedAt);
  const day = date.toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo" });
  const time = date.toLocaleTimeString("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit" });
  return `Versão ${RELEASE.version} · ${day} às ${time}`;
}
