/**
 * Versão do app, exibida no fim do menu. Atualizar a cada update, junto com o arquivo
 * do changelog (pasta changelog/), que tem a mesma versão, data e hora.
 */
export const RELEASE = {
  version: "1.8.0.1",
  // Data e hora (Brasília) em que o update foi publicado.
  releasedAt: "2026-11-14T17:05:00-03:00",
};

/** Mostrado uma vez em "Novidades" depois do update (curto: o detalhe fica no changelog). */
export const RELEASE_NOTES: { title: string; text: string }[] = [
  { title: "Termo pronto para entregar.", text: "Com cláusulas, assinaturas e testemunhas; nome, CPF e endereço das partes são opcionais." },
  { title: "Cobrar com mensagem pronta.", text: "Lembrete, cobrança ou resumo com a sua chave Pix, para mandar no WhatsApp ou copiar." },
  { title: "Pagou a mais?", text: "Escolha abater do fim (termina antes) ou adiantar a próxima, ou mude o valor das parcelas." },
];

export function releaseLabel(): string {
  const date = new Date(RELEASE.releasedAt);
  const day = date.toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo" });
  const time = date.toLocaleTimeString("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit" });
  return `Versão ${RELEASE.version} · ${day} às ${time}`;
}
