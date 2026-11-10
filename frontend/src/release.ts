/**
 * Versão do app, exibida no fim do menu. Atualizar a cada update, junto com o arquivo
 * do changelog (pasta changelog/), que tem a mesma versão, data e hora.
 */
export const RELEASE = {
  version: "1.7.5",
  // Data e hora (Brasília) em que o update foi publicado.
  releasedAt: "2026-11-10T18:00:00-03:00",
};

/** Mostrado uma vez em "Novidades" depois do update (curto: o detalhe fica no changelog). */
export const RELEASE_NOTES: { title: string; text: string }[] = [
  { title: "Painel vivo.", text: "Saudação com o resumo de agora, linha do mês com os vencimentos e avisos num formato só." },
  { title: "Menu recolhível.", text: "Recolha o menu lateral para ganhar espaço (botão ao lado do logo ou Ctrl+B)." },
  { title: "Tire sua dúvida lembra.", text: "Entende mais perguntas, continua a conversa e guarda o histórico por 30 dias." },
];

export function releaseLabel(): string {
  const date = new Date(RELEASE.releasedAt);
  const day = date.toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo" });
  const time = date.toLocaleTimeString("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit" });
  return `Versão ${RELEASE.version} · ${day} às ${time}`;
}
