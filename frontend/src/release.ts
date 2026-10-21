/**
 * Versão do app, exibida no fim do menu. Atualizar a cada update, junto com o arquivo
 * do changelog (pasta changelog/), que tem a mesma versão, data e hora.
 */
export const RELEASE = {
  version: "1.3.0",
  // Data e hora (Brasília) em que o update foi publicado.
  releasedAt: "2026-10-21T10:45:00-03:00",
};

/** Mostrado uma vez em "Novidades" depois do update (curto: o detalhe fica no changelog). */
export const RELEASE_NOTES: { title: string; text: string }[] = [
  { title: "Voz e foto.", text: "Lance falando no lançamento rápido ou leia o comprovante pela foto." },
  { title: "Sem internet.", text: "Lançamentos feitos offline ficam no aparelho e sobem sozinhos depois." },
  { title: "Dividir em categorias.", text: "Uma compra, várias categorias, cada uma com o seu valor." },
  { title: "Desafios e plano sem culpa.", text: "Desafios de economia em Metas e um plano para equilibrar o mês." },
];

export function releaseLabel(): string {
  const date = new Date(RELEASE.releasedAt);
  const day = date.toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo" });
  const time = date.toLocaleTimeString("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit" });
  return `Versão ${RELEASE.version} · ${day} às ${time}`;
}
