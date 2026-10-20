/**
 * Versão do app, exibida no fim do menu. Atualizar a cada update, junto com o arquivo
 * do changelog (pasta changelog/), que tem a mesma versão, data e hora.
 */
export const RELEASE = {
  version: "0.9.0",
  // Data e hora (Brasília) em que o update foi publicado.
  releasedAt: "2026-10-20T13:30:00-03:00",
};

/** Mostrado uma vez em "Novidades" depois do update (curto: o detalhe fica no changelog). */
export const RELEASE_NOTES: { title: string; text: string }[] = [
  { title: "Mensagens.", text: "Respostas às suas solicitações e recados da administração chegam na nova caixa de Mensagens do menu." },
  { title: "Tema na conta.", text: "Claro, escuro ou automático pelo botão rápido do menu, valendo em todos os seus aparelhos." },
  { title: "Começar do zero.", text: "Em Perfil, escolha quais áreas voltam ao padrão, com backup antes e confirmação." },
];

export function releaseLabel(): string {
  const date = new Date(RELEASE.releasedAt);
  const day = date.toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo" });
  const time = date.toLocaleTimeString("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit" });
  return `Versão ${RELEASE.version} · ${day} às ${time}`;
}
