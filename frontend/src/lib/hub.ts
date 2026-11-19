export type SolutionStatus = "active" | "soon";

export type SolutionIcon = "wallet" | "layers";

export interface HubSolution {
  /** Identificador único da solução (base para permissões e futuras integrações entre módulos). */
  id: string;
  /** Nome exibido no cartão do Hub. */
  name: string;
  /** Resumo curto do que a solução faz. */
  description: string;
  /** Etiqueta de disponibilidade exibida no cartão. */
  badge: string;
  /** Estado atual da solução no servidor. */
  status: SolutionStatus;
  /** Rota inicial quando ativa; null enquanto estiver em preparação. */
  to: string | null;
  /** Ícone do catálogo, resolvido pela camada visual do Hub. */
  icon: SolutionIcon;
  /** Chamada exibida na ação do cartão. */
  actionLabel: string;
  /** Soluções com as quais este módulo troca contexto ou dados no futuro. */
  integratesWith?: string[];
}

/**
 * Catálogo central de aplicações do servidor.
 * Para adicionar uma nova solução no Hub, registre uma nova entrada aqui.
 */
export const HUB_SOLUTIONS: HubSolution[] = [
  {
    id: "meu-orcamento",
    name: "Meu Orçamento",
    description: "Orçamento do mês, contas, cartões, metas, investimentos, divisões e assistente local.",
    badge: "Disponível",
    status: "active",
    to: "/orcamento",
    icon: "wallet",
    actionLabel: "Abrir",
  },
  {
    id: "proxima-solucao",
    name: "Nova solução",
    description: "Espaço reservado para o próximo módulo conectado à sua conta e integrável ao Meu Orçamento.",
    badge: "Em breve",
    status: "soon",
    to: null,
    icon: "layers",
    actionLabel: "Em breve",
    integratesWith: ["meu-orcamento"],
  },
];

export function activeSolutions(solutions: HubSolution[] = HUB_SOLUTIONS): HubSolution[] {
  return solutions.filter((item) => item.status === "active" && item.to !== null);
}

export function findSolution(id: string, solutions: HubSolution[] = HUB_SOLUTIONS): HubSolution | undefined {
  return solutions.find((item) => item.id === id);
}

export function defaultSolutionRoute(solutions: HubSolution[] = HUB_SOLUTIONS): string {
  return activeSolutions(solutions)[0]?.to ?? "/orcamento";
}
