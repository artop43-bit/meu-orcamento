/**
 * Painel do Orçamento personalizado (v1.3): quais cartões aparecem e em que ordem.
 * Fica salvo na conta (vale em todos os aparelhos). A lista de despesas não sai do painel.
 */

export type DashboardKey = "quick" | "kpis" | "consultant" | "alerts" | "daily" | "goal" | "incomes" | "breakdown";
export type DashboardCard = { key: DashboardKey; visible: boolean };
export type DashboardArea = "top" | "side";

export const CARDS: { key: DashboardKey; label: string; area: DashboardArea }[] = [
  { key: "quick", label: "Lançamento rápido", area: "top" },
  { key: "kpis", label: "Resumo do mês (receitas, despesas e saldo)", area: "top" },
  { key: "consultant", label: "Desempenho do mês", area: "top" },
  { key: "alerts", label: "Atenção (alertas do mês)", area: "side" },
  { key: "daily", label: "Disponível hoje e saldo previsto", area: "side" },
  { key: "goal", label: "Meta principal", area: "side" },
  { key: "incomes", label: "Receitas", area: "side" },
  { key: "breakdown", label: "Despesas por categoria", area: "side" },
];

export const DEFAULT_DASHBOARD: DashboardCard[] = CARDS.map((c) => ({ key: c.key, visible: true }));

/** Lê o que está salvo; cartões novos (de versões futuras) entram no fim, visíveis. */
export function readDashboard(saved: string | null | undefined): DashboardCard[] {
  let list: DashboardCard[] = [];
  try {
    const parsed = saved ? JSON.parse(saved) : null;
    if (Array.isArray(parsed)) list = parsed.filter((c) => CARDS.some((k) => k.key === c?.key)).map((c) => ({ key: c.key, visible: Boolean(c.visible) }));
  } catch {
    list = [];
  }
  const missing = DEFAULT_DASHBOARD.filter((d) => !list.some((c) => c.key === d.key));
  return [...list, ...missing];
}

export function areaOf(key: DashboardKey): DashboardArea {
  return CARDS.find((c) => c.key === key)!.area;
}

export function labelOf(key: DashboardKey): string {
  return CARDS.find((c) => c.key === key)!.label;
}

/** Move um cartão para cima (-1) ou para baixo (1) dentro da mesma área. */
export function move(list: DashboardCard[], key: DashboardKey, dir: -1 | 1): DashboardCard[] {
  const area = areaOf(key);
  const same = list.filter((c) => areaOf(c.key) === area);
  const index = same.findIndex((c) => c.key === key);
  const target = index + dir;
  if (target < 0 || target >= same.length) return list;
  const swapped = [...same];
  [swapped[index], swapped[target]] = [swapped[target]!, swapped[index]!];
  const other = list.filter((c) => areaOf(c.key) !== area);
  return area === "top" ? [...swapped, ...other] : [...other, ...swapped];
}
