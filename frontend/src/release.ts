import { areaForPath } from "./lib/hub";
import { releaseSolutionLabel, RELEASE_SOLUTIONS, type ReleaseSolutionId } from "./lib/releases";

/**
 * Versão de cada solução, exibida no fim do menu dela. Cada solução tem a própria numeração.
 * Atualizar a cada update, junto com o arquivo do changelog (pasta changelog/) e a entrada em
 * lib/releases.ts, que têm a mesma versão, data e hora.
 */
export type SolutionRelease = {
  version: string;
  /** Data e hora (Brasília, ISO com -03:00) da publicação; null enquanto a versão está em preparação. */
  releasedAt: string | null;
  /** Mostrado uma vez em "Novidades" depois do update, só dentro da solução (curto: o detalhe fica no changelog). */
  notes: { title: string; text: string }[];
};

export const SOLUTION_RELEASES: Record<ReleaseSolutionId, SolutionRelease> = {
  hub: {
    version: "1.0.0",
    releasedAt: null,
    notes: [
      { title: "Termos e privacidade do Hub.", text: "Veja quais dados as nove soluções usam, inclusive o Cofre e o Caderno, e como exercer seus direitos." },
      { title: "Hub de Soluções.", text: "Depois de entrar, escolha a solução: Meu Orçamento, Mensageria, Dashboard & CRM, Catálogo & Estoque, Propostas & PDFs, Projetos & Tarefas, Agenda 360°, Cofre & Garantias ou Caderno." },
      { title: "Conta num lugar só.", text: "Perfil, segurança, aparência, app e notas da versão ficam nas Configurações do Hub." },
      { title: "Sair volta ao Hub.", text: "Dentro de uma solução, o botão Sair leva de volta ao Hub sem encerrar a sessão." },
    ],
  },
  "meu-orcamento": {
    version: "1.11.0",
    releasedAt: null,
    notes: [
      { title: "Reforma Tributária em Análises.", text: "Simule IBS, CBS e Imposto Seletivo, consulte tabelas da Receita e gere o PDF de uma nota de serviço." },
      { title: "Comece por Análises.", text: "O guia do primeiro mês fica legível no celular antes dos primeiros lançamentos." },
      {
        title: "Tire sua dúvida mais esperto.",
        text: "Entende perguntas com vários filtros juntos (período, cartão, conta, valor) e acha qualquer lançamento: “onde está o lançamento X?”.",
      },
      { title: "Ajustes só do orçamento.", text: "Perfil, segurança e aparência agora ficam nas Configurações do Hub." },
      { title: "Retrospectiva em Análises.", text: "As médias dos meses e a retrospectiva para compartilhar ficam em Análises › Retrospectiva." },
    ],
  },
  mensageria: {
    version: "1.0.0",
    releasedAt: null,
    notes: [
      { title: "WhatsApp por QR Code.", text: "Conecte o seu número e converse por aqui, com fotos, áudios, vídeos e documentos." },
      { title: "Atendimento na conversa.", text: "Etiquetas, lembrete de retorno, respostas rápidas com / e o botão Lançar, que registra o valor no Meu Orçamento." },
      { title: "Conexão com acesso restrito.", text: "O conector pode usar um acesso ao banco separado do restante do Hub." },
    ],
  },
  "dashboard-crm": {
    version: "1.0.0",
    releasedAt: null,
    notes: [
      { title: "Painéis do seu jeito.", text: "Gráficos com os dados do CRM, da Mensageria e do Meu Orçamento, a partir de modelos prontos." },
      { title: "Funil de vendas e contatos.", text: "Negócios por etapa e contatos trazidos das conversas da Mensageria." },
      { title: "PDF e CSV.", text: "Leia as tabelas de arquivos PDF e CSV, com prévia para conferir antes de importar." },
    ],
  },
  catalogo: {
    version: "1.0.0",
    releasedAt: null,
    notes: [
      { title: "Produtos, serviços e margem.", text: "Cadastre itens com custo, venda, saldo em estoque e alertas de reposição." },
      { title: "Itens mais legíveis.", text: "Os nomes têm mais espaço e o código fica em uma linha própria." },
      { title: "Pedidos integrados.", text: "Baixe o estoque ao confirmar e lance a receita no Meu Orçamento e no CRM." },
    ],
  },
  propostas: {
    version: "1.0.0",
    releasedAt: null,
    notes: [
      { title: "Documentos profissionais em PDF.", text: "Gere propostas, ordens de serviço, contratos e recibos localmente em A4." },
      { title: "Envio direto no WhatsApp.", text: "Envie o PDF na Mensageria e aprove criando receita no Orçamento e negócio ganho." },
      { title: "Mais espaço para o título.", text: "No celular, o preço fica abaixo do título do documento." },
    ],
  },
  projetos: {
    version: "1.0.0",
    releasedAt: null,
    notes: [
      { title: "Kanban e apontamento de horas.", text: "Acompanhe entregas com checklists e descubra sua margem e valor real por hora." },
      { title: "Edite pelo cartão do projeto.", text: "Abra um projeto para editar seus dados ou excluir com opção de desfazer." },
      { title: "Integrado ao CRM, Propostas e WhatsApp.", text: "Crie projetos em 1 clique e transforme mensagens em tarefas." },
    ],
  },
  agenda: {
    version: "1.0.0",
    releasedAt: null,
    notes: [
      { title: "Agenda 360° do Hub.", text: "Veja compromissos, follow-ups do WhatsApp, CRM, entregas, garantias e contas na mesma linha do tempo." },
      { title: "Confirmação pelo WhatsApp.", text: "Prepare e envie lembretes direto na conversa do cliente pela Mensageria." },
      { title: "Agenda no celular.", text: "O período fica mais curto e os controles de visualização e camadas ficam em uma linha cada." },
    ],
  },
  cofre: {
    version: "1.0.0",
    releasedAt: null,
    notes: [
      { title: "Arquivo permanente e OCR local.", text: "Guarde PDFs, notas fiscais e garantias com leitura de texto para busca e alertas na Agenda." },
      { title: "Proteção da Mensageria.", text: "Salve mídias do WhatsApp e PDFs de propostas no Cofre com 1 toque." },
    ],
  },
  caderno: {
    version: "1.0.0",
    releasedAt: null,
    notes: [
      { title: "Notas conectadas com [[…]].", text: "Escreva em Markdown com modelos prontos, links bidirecionais e busca BM25 local." },
      { title: "Roteiros na Mensageria.", text: "Puxe roteiros comerciais e POPs direto dentro do atendimento no chat." },
    ],
  },
};

export function releaseOf(solution: ReleaseSolutionId): SolutionRelease {
  return SOLUTION_RELEASES[solution];
}

/** "dd/mm/aaaa às hh:mm" no horário de Brasília, ou "Em preparação" para a versão ainda não publicada. */
export function releaseDateLabel(releasedAt: string | null): string {
  if (!releasedAt) return "Em preparação";
  const date = new Date(releasedAt);
  const day = date.toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo" });
  const time = date.toLocaleTimeString("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit" });
  return `${day} às ${time}`;
}

/** Texto do fim do menu de cada solução: "Versão 1.11.0 · 17/11/2026 às 21:20" ou "Versão 1.0.0 · Em preparação". */
export function releaseLabel(solution: ReleaseSolutionId): string {
  const release = releaseOf(solution);
  return `Versão ${release.version} · ${releaseDateLabel(release.releasedAt)}`;
}

// ---------------------------------------------------------------- versão em relatórios

/** Nome curto da solução nos relatórios de erro e nas solicitações (o servidor aceita até 20 caracteres). */
const REPORT_TAG: Record<ReleaseSolutionId, string> = {
  hub: "Hub",
  "meu-orcamento": "Orçamento",
  mensageria: "Mensageria",
  "dashboard-crm": "CRM",
  catalogo: "Catálogo",
  propostas: "Propostas",
  projetos: "Projetos",
  agenda: "Agenda",
  cofre: "Cofre",
  caderno: "Caderno",
};

export const RELEASE_TAG_MAX = 20;

/** Solução e versão num texto curto, ex.: "Orçamento 1.11.0" (vai para Administração › Erros e › Solicitações). */
export function releaseTag(solution: ReleaseSolutionId): string {
  return `${REPORT_TAG[solution]} ${releaseOf(solution).version}`.slice(0, RELEASE_TAG_MAX);
}

/**
 * Solução dona de um endereço, para saber de qual versão falar. As páginas abertas sem login
 * (entrar, cadastro, termos...) e as telas da conta são do Hub de Soluções.
 */
export function releaseSolutionForPath(pathname: string): ReleaseSolutionId {
  const area = areaForPath(pathname);
  return RELEASE_SOLUTIONS.find((item) => item.id === area)?.id ?? "hub";
}

/** Rótulo para quem lê: "Meu Orçamento 1.11.0". */
export function releaseNameAndVersion(solution: ReleaseSolutionId): string {
  return `${releaseSolutionLabel(solution)} ${releaseOf(solution).version}`;
}

// ---------------------------------------------------------------- aviso "Novidades"

/** Chave antiga, de quando só existia o Meu Orçamento: guarda a última versão vista dele. */
export const LEGACY_SEEN_KEY = "novidades-vistas";

/** Uma chave de "já visto" por solução; o valor é a versão vista. */
export function whatsNewSeenKey(solution: ReleaseSolutionId): string {
  return `${LEGACY_SEEN_KEY}:${solution}`;
}

type SeenStorage = Pick<Storage, "getItem" | "setItem">;

/**
 * Decide se o aviso de Novidades da solução aparece agora. Aparece uma vez por versão e só na
 * própria solução. Conta nova (nada visto em lugar nenhum) vê o tour, não as novidades: a versão
 * atual fica marcada como vista. Quem já usava o app antes da separação por solução tem só a chave
 * antiga: ela vale como a versão vista do Meu Orçamento, e as outras soluções ainda são novidade.
 */
export function shouldShowWhatsNew(solution: ReleaseSolutionId, storage: SeenStorage): boolean {
  const current = releaseOf(solution).version;
  const key = whatsNewSeenKey(solution);
  const seen = storage.getItem(key);
  if (seen !== null) return seen !== current;
  const legacy = storage.getItem(LEGACY_SEEN_KEY);
  if (legacy === null) {
    storage.setItem(key, current);
    return false;
  }
  if (solution === "meu-orcamento" && legacy === current) {
    storage.setItem(key, current);
    return false;
  }
  return true;
}

/** Marca as Novidades da versão atual da solução como vistas (não volta a aparecer). */
export function markWhatsNewSeen(solution: ReleaseSolutionId, storage: SeenStorage): void {
  storage.setItem(whatsNewSeenKey(solution), releaseOf(solution).version);
}
