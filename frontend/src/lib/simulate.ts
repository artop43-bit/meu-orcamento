/** Cenário do simulador "e se": variações sobre a renda e as contas de um mês. */
export type Sim = {
  /** Variação da renda, em % (ex.: 10 = +10%). */
  incomePct: number;
  /** Variação de todas as contas, em %. */
  expensePct: number;
  /** Corte nos gastos não essenciais, em % (0 a 100). */
  cutWantsPct: number;
  /** Nova conta mensal, em reais. */
  extra: number;
};

export const ZERO_SIM: Sim = { incomePct: 0, expensePct: 0, cutWantsPct: 0, extra: 0 };

/**
 * Aplica o cenário a um mês. `wants` é quanto das contas é não essencial:
 * o corte incide só sobre essa parte, antes da variação geral das contas.
 */
export function simulate(point: { income: number; expenses: number }, wants: number, sim: Sim) {
  const income = point.income * (1 + sim.incomePct / 100);
  const cut = wants * (sim.cutWantsPct / 100);
  const expenses = Math.max(0, (point.expenses - cut) * (1 + sim.expensePct / 100) + sim.extra);
  return { income, expenses, balance: income - expenses };
}

/** Saldo acumulado mês a mês aplicando o mesmo cenário a cada ponto da projeção. */
export function cumulativeBalance(
  points: { income: number; expenses: number; nonEssential: number }[],
  sim: Sim,
): number[] {
  let total = 0;
  return points.map((p) => {
    total += simulate(p, p.nonEssential, sim).balance;
    return total;
  });
}
