/**
 * Versão do app, exibida no fim do menu. Atualizar a cada update, junto com o arquivo
 * do changelog (pasta changelog/), que tem a mesma versão, data e hora.
 */
export const RELEASE = {
  version: "1.2.0",
  // Data e hora (Brasília) em que o update foi publicado.
  releasedAt: "2026-10-21T00:20:00-03:00",
};

/** Mostrado uma vez em "Novidades" depois do update (curto: o detalhe fica no changelog). */
export const RELEASE_NOTES: { title: string; text: string }[] = [
  { title: "Navegação fluida.", text: "As telas abrem na hora, sem piscar, e os dados chegam antes do clique." },
  { title: "Vários grupos abertos.", text: "Abra Carteira, Planejamento e Análises juntos; o menu lembra o que ficou aberto." },
  { title: "Cores consistentes.", text: "O positivo agora segue a cor de destaque escolhida; o vermelho fica só para o negativo." },
];

export function releaseLabel(): string {
  const date = new Date(RELEASE.releasedAt);
  const day = date.toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo" });
  const time = date.toLocaleTimeString("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit" });
  return `Versão ${RELEASE.version} · ${day} às ${time}`;
}
