/**
 * Versão do app, exibida no fim do menu. Atualizar a cada update, junto com o arquivo
 * do changelog (pasta changelog/), que tem a mesma versão, data e hora.
 */
export const RELEASE = {
  version: "1.9.0",
  // Data e hora (Brasília) em que o update foi publicado.
  releasedAt: "2026-11-15T15:00:00-03:00",
};

/** Mostrado uma vez em "Novidades" depois do update (curto: o detalhe fica no changelog). */
export const RELEASE_NOTES: { title: string; text: string }[] = [
  { title: "Avisos por webhook.", text: "Receba os avisos no Discord, no Slack ou em outro serviço. Escolha quais em Ajustes › Preferências." },
  { title: "Menu recolhido em janelas baixas.", text: "Agora tudo cabe dentro do menu, sem botões saindo para fora." },
  { title: "Divisões.", text: "A pessoa aberta continua aberta depois de lançar uma anotação." },
];

export function releaseLabel(): string {
  const date = new Date(RELEASE.releasedAt);
  const day = date.toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo" });
  const time = date.toLocaleTimeString("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit" });
  return `Versão ${RELEASE.version} · ${day} às ${time}`;
}
