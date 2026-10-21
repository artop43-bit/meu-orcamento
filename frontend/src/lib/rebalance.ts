/**
 * Meta de alocação (v1.4): com o valor de hoje em cada classe e a divisão desejada (%), quanto
 * do próximo aporte vai para cada classe para chegar mais perto do alvo, sem vender nada.
 * Não indica ativos: só a distribuição entre as classes que a própria pessoa escolheu.
 */
export type RebalanceRow = { kind: string; now: number; target: number; desired: number; add: number };

export function rebalance(current: Record<string, number>, targets: Record<string, number>, contribution: number): RebalanceRow[] {
  const kinds = [...new Set([...Object.keys(targets), ...Object.keys(current)])];
  const total = kinds.reduce((sum, k) => sum + (current[k] ?? 0), 0) + Math.max(contribution, 0);
  const rows = kinds.map((kind) => {
    const target = targets[kind] ?? 0;
    const desired = (total * target) / 100;
    return { kind, now: current[kind] ?? 0, target, desired, add: 0 };
  });
  const gaps = rows.map((r) => Math.max(0, r.desired - r.now));
  const gapTotal = gaps.reduce((a, b) => a + b, 0);
  let left = Math.max(contribution, 0);
  if (gapTotal > 0) {
    // Primeiro cobre o que falta em cada classe (proporcionalmente, se não der para tudo).
    const share = Math.min(1, left / gapTotal);
    rows.forEach((r, i) => (r.add = gaps[i]! * share));
    left -= gapTotal * share;
  }
  if (left > 0.005) {
    // O que sobra segue a própria meta.
    const targetTotal = rows.reduce((sum, r) => sum + r.target, 0) || 1;
    rows.forEach((r) => (r.add += (left * r.target) / targetTotal));
  }
  return rows.map((r) => ({ ...r, add: Math.round(r.add * 100) / 100 }));
}
