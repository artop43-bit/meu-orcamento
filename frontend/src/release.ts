/**
 * Versão do app, exibida no fim do menu. Atualizar a cada update, junto com o arquivo
 * do changelog (pasta changelog/), que tem a mesma versão, data e hora.
 */
export const RELEASE = {
  version: "0.7.7",
  // Data e hora (Brasília) em que o update foi publicado.
  releasedAt: "2026-10-19T21:45:00-03:00",
};

/** Mostrado uma vez em "Novidades" depois do update (curto: o detalhe fica no changelog). */
export const RELEASE_NOTES: { title: string; text: string }[] = [
  { title: "E-mails de verdade.", text: "Confirmação de cadastro e redefinição de senha chegam direto na sua caixa de entrada." },
  { title: "Termos e Privacidade completos.", text: "Responsável, contato e foro preenchidos; as páginas deixaram de ser rascunho." },
];

export function releaseLabel(): string {
  const date = new Date(RELEASE.releasedAt);
  const day = date.toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo" });
  const time = date.toLocaleTimeString("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit" });
  return `Versão ${RELEASE.version} · ${day} às ${time}`;
}
