/**
 * Plano de quitação (v1.3): compara duas ordens de pagamento com o mesmo dinheiro por mês.
 *
 * - "Menor dívida primeiro" (bola de neve): quita rápido as pequenas, o que motiva.
 * - "Juros mais altos primeiro" (avalanche): costuma pagar menos juros no total.
 *
 * Todo mês cada dívida rende juros e recebe a parcela mínima; o valor extra vai inteiro para a
 * dívida da vez. Quando uma termina, a parcela dela passa para a próxima (o total por mês não
 * muda). Só mostra números: não recomenda nenhum produto financeiro.
 */

export type PayoffDebt = {
  id: string;
  name: string;
  balance: number;
  /** Taxa ao mês, em fração (0,02 = 2% a.m.). */
  rate: number;
  /** Parcela mínima do mês 1 (Price: fixa; SAC: cai com o saldo; outras: informada). */
  kind: "price" | "sac" | "fixed";
  /** Parcelas que faltam (Price e SAC). */
  remaining?: number;
  /** Parcela informada (dívidas sem sistema de amortização). */
  payment?: number;
};

export type Strategy = "minimum" | "snowball" | "avalanche";

export type PayoffResult = {
  strategy: Strategy;
  /** Meses até quitar tudo; null se não termina em 50 anos (parcela não cobre os juros). */
  months: number | null;
  interest: number;
  /** Mês (1, 2, ...) em que cada dívida termina, na ordem em que terminam. */
  finished: { id: string; name: string; month: number }[];
};

const LIMIT = 600;
const round = (value: number) => Math.round(value * 100) / 100;

function pmt(balance: number, rate: number, n: number): number {
  if (n <= 0) return balance;
  if (rate === 0) return balance / n;
  return (balance * rate) / (1 - (1 + rate) ** -n);
}

export function simulate(debts: PayoffDebt[], extra: number, strategy: Strategy): PayoffResult {
  const open = debts
    .filter((d) => d.balance > 0.005)
    .map((d) => ({
      ...d,
      left: d.balance,
      fixed: d.kind === "price" ? pmt(d.balance, d.rate, d.remaining ?? 1) : d.kind === "fixed" ? (d.payment ?? 0) : 0,
      amortization: d.kind === "sac" ? d.balance / Math.max(d.remaining ?? 1, 1) : 0,
    }));
  const minimum = (d: (typeof open)[number]) => (d.kind === "sac" ? d.amortization + d.left * d.rate : d.fixed);
  // Dinheiro por mês: as parcelas do mês 1 mais o extra (fica igual até o fim).
  const budget = open.reduce((sum, d) => sum + minimum(d), 0) + (strategy === "minimum" ? 0 : extra);
  const finished: PayoffResult["finished"] = [];
  let interest = 0;

  for (let month = 1; month <= LIMIT; month++) {
    const active = open.filter((d) => d.left > 0.005);
    if (active.length === 0) return { strategy, months: month - 1, interest: round(interest), finished };
    let money = budget;
    // Parcela mínima do mês (calculada sobre o saldo antes dos juros do mês).
    const due = new Map(active.map((d) => [d, minimum(d)]));
    for (const d of active) {
      const charged = d.left * d.rate;
      interest += charged;
      d.left += charged;
    }
    // Parcelas mínimas primeiro.
    for (const d of active) {
      const pay = Math.min(due.get(d) ?? 0, d.left, money);
      d.left -= pay;
      money -= pay;
    }
    // O que sobra vai para a dívida da vez (e, se ela acabar, para a seguinte).
    if (strategy !== "minimum") {
      const order = active
        .filter((d) => d.left > 0.005)
        .sort((a, b) => (strategy === "snowball" ? a.left - b.left : b.rate - a.rate || a.left - b.left));
      for (const d of order) {
        if (money <= 0.005) break;
        const pay = Math.min(money, d.left);
        d.left -= pay;
        money -= pay;
      }
    }
    for (const d of active) {
      if (d.left <= 0.005) {
        d.left = 0;
        finished.push({ id: d.id, name: d.name, month });
      }
    }
  }
  return { strategy, months: null, interest: round(interest), finished };
}

export function comparePlans(debts: PayoffDebt[], extra: number): Record<Strategy, PayoffResult> {
  return {
    minimum: simulate(debts, 0, "minimum"),
    snowball: simulate(debts, extra, "snowball"),
    avalanche: simulate(debts, extra, "avalanche"),
  };
}
