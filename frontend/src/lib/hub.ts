export type SolutionStatus = "active" | "soon";

export type SolutionIcon =
  | "wallet"
  | "messages"
  | "crm"
  | "catalog"
  | "proposals"
  | "projects"
  | "agenda"
  | "vault"
  | "notebook"
  | "layers";

export interface HubSolution {
  /** Identificador único da solução (base para permissões, transições e integrações entre módulos). */
  id: string;
  /** Nome exibido no cartão do Hub e na animação de entrada da solução. */
  name: string;
  /** Resumo curto do que a solução faz. */
  description: string;
  /** Etiqueta de disponibilidade exibida no cartão. */
  badge: string;
  /** Estado atual da solução no servidor. */
  status: SolutionStatus;
  /** Rota inicial quando ativa; null enquanto estiver em preparação. */
  to: string | null;
  /** Ícone do catálogo, resolvido pela camada visual do Hub e pela transição padrão. */
  icon: SolutionIcon;
  /** Chamada exibida na ação do cartão. */
  actionLabel: string;
  /** Prefixos de rota pertencentes a esta solução (disparam a transição padrão e barram o salto entre soluções). */
  routePrefixes: string[];
  /** Soluções com as quais este módulo troca contexto ou dados. */
  integratesWith?: string[];
}

/**
 * Catálogo central de aplicações do servidor.
 * Para adicionar uma nova solução no Hub (com cartão e transição padrão), registre uma entrada aqui.
 */
export const HUB_SOLUTIONS: HubSolution[] = [
  {
    id: "meu-orcamento",
    name: "Meu Orçamento",
    description: "Orçamento do mês, contas, cartões, metas, investimentos e divisões.",
    badge: "Disponível",
    status: "active",
    to: "/orcamento",
    icon: "wallet",
    actionLabel: "Abrir",
    routePrefixes: [
      "/orcamento",
      "/calendario",
      "/cartoes",
      "/contas",
      "/revisar",
      "/busca",
      "/dividas",
      "/divisoes",
      "/metas",
      "/historico",
      "/analises",
      "/investimentos",
      "/ajustes",
      "/relatorio",
    ],
  },
  {
    id: "mensageria",
    name: "Mensageria",
    description: "Troca de mensagens integrada ao WhatsApp Web e ao Meu Orçamento.",
    badge: "Disponível",
    status: "active",
    to: "/mensageria",
    icon: "messages",
    actionLabel: "Abrir",
    routePrefixes: ["/mensageria"],
    integratesWith: ["meu-orcamento", "dashboard-crm"],
  },
  {
    id: "dashboard-crm",
    name: "Dashboard & CRM",
    description: "Painéis personalizados, funil de vendas, PDF/CSV e APIs integrados ao Hub.",
    badge: "Disponível",
    status: "active",
    to: "/crm",
    icon: "crm",
    actionLabel: "Abrir",
    routePrefixes: ["/crm"],
    integratesWith: ["meu-orcamento", "mensageria", "catalogo", "propostas"],
  },
  {
    id: "catalogo",
    name: "Catálogo & Estoque",
    description: "Produtos, serviços, margens, reposição e pedidos ligados ao Orçamento e ao CRM.",
    badge: "Disponível",
    status: "active",
    to: "/catalogo",
    icon: "catalog",
    actionLabel: "Abrir",
    routePrefixes: ["/catalogo"],
    integratesWith: ["meu-orcamento", "dashboard-crm", "propostas"],
  },
  {
    id: "propostas",
    name: "Propostas & PDFs",
    description: "Orçamentos, ordens de serviço, contratos e recibos em PDF enviados no WhatsApp.",
    badge: "Disponível",
    status: "active",
    to: "/propostas",
    icon: "proposals",
    actionLabel: "Abrir",
    routePrefixes: ["/propostas"],
    integratesWith: ["catalogo", "dashboard-crm", "mensageria", "meu-orcamento", "projetos"],
  },
  {
    id: "projetos",
    name: "Projetos & Tarefas",
    description: "Kanban de entregas, checklists, horas trabalhadas e rentabilidade ligada ao Orçamento.",
    badge: "Disponível",
    status: "active",
    to: "/projetos",
    icon: "projects",
    actionLabel: "Abrir",
    routePrefixes: ["/projetos"],
    integratesWith: ["meu-orcamento", "dashboard-crm", "propostas", "mensageria", "agenda"],
  },
  {
    id: "agenda",
    name: "Agenda & Compromissos",
    description: "Visão 360° de compromissos, follow-ups, prazos, CRM, Cofre e vencimentos do Orçamento.",
    badge: "Disponível",
    status: "active",
    to: "/agenda",
    icon: "agenda",
    actionLabel: "Abrir",
    routePrefixes: ["/agenda"],
    integratesWith: ["mensageria", "dashboard-crm", "projetos", "meu-orcamento", "cofre"],
  },
  {
    id: "cofre",
    name: "Cofre & Garantias",
    description: "Arquivo permanente de PDFs e fotos com busca por OCR local, validades e proteção do WhatsApp.",
    badge: "Disponível",
    status: "active",
    to: "/cofre",
    icon: "vault",
    actionLabel: "Abrir",
    routePrefixes: ["/cofre"],
    integratesWith: ["mensageria", "propostas", "agenda", "dashboard-crm", "projetos"],
  },
  {
    id: "caderno",
    name: "Caderno & Conhecimento",
    description: "Notas em Markdown, links [[...]], modelos prontos, roteiros e busca BM25 instantânea.",
    badge: "Disponível",
    status: "active",
    to: "/caderno",
    icon: "notebook",
    actionLabel: "Abrir",
    routePrefixes: ["/caderno"],
    integratesWith: ["dashboard-crm", "projetos", "mensageria", "cofre", "meu-orcamento"],
  },
];

export function activeSolutions(solutions: HubSolution[] = HUB_SOLUTIONS): HubSolution[] {
  return solutions.filter((item) => item.status === "active" && item.to !== null);
}

export function findSolution(id: string, solutions: HubSolution[] = HUB_SOLUTIONS): HubSolution | undefined {
  return solutions.find((item) => item.id === id);
}

/** Confere se uma solução está bloqueada pelo administrador para a conta atual. */
export function isSolutionBlocked(
  solutionId: string,
  blockedResources?: readonly string[] | null,
): boolean {
  if (!blockedResources || blockedResources.length === 0) return false;
  return blockedResources.includes(solutionId);
}

function matchesPrefix(pathname: string, prefix: string): boolean {
  return pathname === prefix || pathname.startsWith(`${prefix}/`);
}

/** Identifica a qual solução pertence um endereço (ou null para rotas do próprio Hub). */
export function solutionForPath(pathname: string, solutions: HubSolution[] = HUB_SOLUTIONS): HubSolution | null {
  for (const solution of solutions) {
    if (solution.status !== "active") continue;
    if (solution.routePrefixes.some((prefix) => matchesPrefix(pathname, prefix))) {
      return solution;
    }
  }
  return null;
}

// ---------------------------------------------------------------- áreas do app

/** Área do Hub de Soluções: conta, configurações, mensagens da plataforma e administração. */
export const HUB_AREA = "hub";

/** Páginas abertas sem login (ou a partir de links de e-mail): não contam como área visitada. */
const PUBLIC_PREFIXES = [
  "/entrar",
  "/cadastro",
  "/esqueci-senha",
  "/verificar-email",
  "/redefinir-senha",
  "/privacidade",
  "/termos",
  "/descadastrar",
  "/nao-fui-eu",
];

/** Endereços que começam como os de uma solução, mas abrem telas da conta (fora da moldura da solução). */
const HUB_PREFIXES_INSIDE_SOLUTIONS = [
  "/ajustes/perfil",
  "/ajustes/seguranca",
  "/ajustes/app",
  "/ajustes/notas",
  "/ajustes/solicitacoes",
];

/**
 * Em que área do app fica um endereço: o id da solução, "hub" (telas da conta e da plataforma)
 * ou null para as páginas públicas (entrar, cadastro, termos...).
 */
export function areaForPath(pathname: string, solutions: HubSolution[] = HUB_SOLUTIONS): string | null {
  if (PUBLIC_PREFIXES.some((prefix) => matchesPrefix(pathname, prefix))) return null;
  if (HUB_PREFIXES_INSIDE_SOLUTIONS.some((prefix) => matchesPrefix(pathname, prefix))) return HUB_AREA;
  return solutionForPath(pathname, solutions)?.id ?? HUB_AREA;
}

/** A área é uma solução ativa do catálogo (e não o Hub nem uma página pública). */
export function isSolutionArea(area: string | null, solutions: HubSolution[] = HUB_SOLUTIONS): boolean {
  if (area === null || area === HUB_AREA) return false;
  return solutions.some((item) => item.id === area && item.status === "active");
}

/**
 * Pular de uma solução direto para outra (link interno ou voltar/avançar do navegador) não é
 * permitido: a pessoa passa antes pelo Hub. Vale só quando as duas áreas são soluções diferentes.
 * Sem área anterior (endereço digitado, favorito, notificação) a solução abre direto.
 */
export function shouldBlockSolutionJump(
  prevArea: string | null,
  nextArea: string | null,
  solutions: HubSolution[] = HUB_SOLUTIONS,
): boolean {
  return isSolutionArea(prevArea, solutions) && isSolutionArea(nextArea, solutions) && prevArea !== nextArea;
}

/**
 * Solução cuja animação de entrada deve tocar numa troca de área: só quando se chega a uma
 * solução vindo do Hub (o salto entre soluções é barrado antes, e página pública não anima).
 */
export function splashSolutionForAreas(
  prevArea: string | null,
  nextArea: string | null,
  solutions: HubSolution[] = HUB_SOLUTIONS,
): HubSolution | null {
  if (prevArea !== HUB_AREA || !isSolutionArea(nextArea, solutions)) return null;
  return solutions.find((item) => item.id === nextArea) ?? null;
}

// ---------------------------------------------------------------- tempos da transição

export interface SplashTiming {
  /** Depois do clique no cartão, tempo mínimo antes de trocar de tela (a animação começa a tocar). */
  navigateMinMs: number;
  /** Limite para trocar de tela mesmo que o código da tela ainda não tenha chegado. */
  navigateMaxMs: number;
  /** Tempo mínimo que a animação fica na tela (logo → nome → barra). */
  visibleMinMs: number;
  /** Limite: a animação nunca fica mais que isto, mesmo que a tela demore. */
  visibleMaxMs: number;
  /** Duração da saída da animação (esmaece e aproxima de leve). */
  exitMs: number;
  /** Duração da entrada do conteúdo da solução, por baixo da animação que sai. */
  contentMs: number;
}

export const SOLUTION_SPLASH_TIMING: SplashTiming = {
  navigateMinMs: 520,
  navigateMaxMs: 1500,
  visibleMinMs: 720,
  visibleMaxMs: 2500,
  exitMs: 320,
  contentMs: 440,
};

/** "Reduzir movimento": o app desliga as animações; a marca da solução aparece só por um instante. */
export const SOLUTION_SPLASH_TIMING_REDUCED: SplashTiming = {
  navigateMinMs: 0,
  navigateMaxMs: 1500,
  visibleMinMs: 240,
  visibleMaxMs: 2500,
  exitMs: 120,
  contentMs: 0,
};

/** Saída de uma solução para o Hub: a tela esmaece por este tempo antes de trocar. */
export const SOLUTION_LEAVE_MS = 200;

export function splashTiming(reducedMotion: boolean): SplashTiming {
  return reducedMotion ? SOLUTION_SPLASH_TIMING_REDUCED : SOLUTION_SPLASH_TIMING;
}

/**
 * Quando trocar de tela depois do clique no cartão (ms contados do clique): depois do mínimo e
 * do código da tela pronto, o que vier por último; nunca depois do limite. `chunkReadyAfterMs`
 * null = o código ainda não chegou.
 */
export function navigateDelay(chunkReadyAfterMs: number | null, timing: SplashTiming = SOLUTION_SPLASH_TIMING): number {
  if (chunkReadyAfterMs === null) return timing.navigateMaxMs;
  return Math.min(timing.navigateMaxMs, Math.max(timing.navigateMinMs, chunkReadyAfterMs));
}

/**
 * Com a tela da solução já montada, quanto esperar (ms) para a animação começar a sair:
 * completa o tempo mínimo visível e nunca passa do limite.
 */
export function computeSplashExitDelay(elapsedMs: number, timing: SplashTiming = SOLUTION_SPLASH_TIMING): number {
  const untilMin = timing.visibleMinMs - elapsedMs;
  const untilMax = timing.visibleMaxMs - elapsedMs;
  return Math.max(0, Math.min(untilMin, untilMax));
}

/**
 * Logo depois de a animação aparecer, um clique nela ainda não pula a entrada: quem clica duas
 * vezes no cartão (hábito comum) acertaria a animação com o segundo clique sem querer.
 */
export const SOLUTION_SPLASH_SKIP_GUARD_MS = 350;

/**
 * O clique na animação pula a entrada? Não vale o segundo clique de um duplo clique
 * (`clickCount` = `event.detail` > 1) nem um clique logo depois de a animação aparecer.
 * Esc pula a qualquer momento (não passa por aqui).
 */
export function canSkipSplashByClick(elapsedMs: number, clickCount: number): boolean {
  return clickCount <= 1 && elapsedMs >= SOLUTION_SPLASH_SKIP_GUARD_MS;
}

/**
 * "Sair" de uma solução: depois do esmaecimento, ainda vale voltar ao Hub? Só se a pessoa
 * continua na mesma solução (uma troca de conversa ou de aba dentro dela não cancela a saída);
 * se já foi para outra área (voltar do navegador, por exemplo), não puxa de volta para o Hub.
 */
export function leaveStillApplies(
  fromPath: string,
  currentPath: string,
  solutions: HubSolution[] = HUB_SOLUTIONS,
): boolean {
  const fromArea = areaForPath(fromPath, solutions);
  return isSolutionArea(fromArea, solutions) && areaForPath(currentPath, solutions) === fromArea;
}

/** Clique simples com o botão principal: com Ctrl, Shift, Alt ou ⌘ o link abre como o navegador manda. */
export function isPlainLeftClick(event: {
  button: number;
  metaKey: boolean;
  altKey: boolean;
  ctrlKey: boolean;
  shiftKey: boolean;
  defaultPrevented: boolean;
}): boolean {
  return (
    event.button === 0 && !event.defaultPrevented && !event.metaKey && !event.altKey && !event.ctrlKey && !event.shiftKey
  );
}
