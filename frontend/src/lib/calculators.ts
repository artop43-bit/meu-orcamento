/**
 * Calculadoras financeiras (v1.0). Juros compostos com capitalização mensal; taxas em % ao mês
 * ou ao ano (convertidas por (1 + a)^(1/12) − 1). Só contas: nenhuma recomenda produto.
 */

export type RatePeriod = "monthly" | "yearly";

export function toMonthly(rate: number, period: RatePeriod): number {
  const r = rate / 100;
  return period === "yearly" ? (1 + r) ** (1 / 12) - 1 : r;
}

const round2 = (v: number) => Math.round(v * 100) / 100;

/** Juros compostos: valor inicial + aportes mensais (no fim de cada mês). */
export function compound(initial: number, monthly: number, ratePct: number, period: RatePeriod, months: number) {
  const i = toMonthly(ratePct, period);
  let balance = initial;
  const points: number[] = [];
  for (let m = 1; m <= months; m++) {
    balance = balance * (1 + i) + monthly;
    points.push(round2(balance));
  }
  const invested = initial + monthly * months;
  return { final: round2(balance), invested: round2(invested), interest: round2(balance - invested), points };
}

/** Quanto guardar por mês para chegar a `target` em `months` meses (já tendo `current`). */
export function savingPlan(target: number, current: number, ratePct: number, period: RatePeriod, months: number) {
  const i = toMonthly(ratePct, period);
  if (months <= 0) return { monthly: Math.max(0, target - current), interest: 0 };
  const grown = current * (1 + i) ** months;
  const missing = target - grown;
  if (missing <= 0) return { monthly: 0, interest: round2(grown - current) };
  const factor = i === 0 ? months : ((1 + i) ** months - 1) / i;
  const monthly = missing / factor;
  return { monthly: round2(monthly), interest: round2(target - current - monthly * months) };
}

/**
 * À vista com desconto ou parcelado sem juros: o dinheiro que fica aplicado enquanto as parcelas
 * são pagas rende. Compara o custo das parcelas trazidas a valor presente com o preço à vista.
 */
export function cashOrInstallments(price: number, discountPct: number, installments: number, ratePct: number, period: RatePeriod) {
  const i = toMonthly(ratePct, period);
  const cash = price * (1 - discountPct / 100);
  const parcel = price / installments;
  let present = 0;
  for (let k = 1; k <= installments; k++) present += parcel / (1 + i) ** k;
  // Desconto mínimo para o à vista empatar com o parcelado.
  const breakEven = (1 - present / price) * 100;
  return {
    cash: round2(cash),
    parcel: round2(parcel),
    installmentsPresent: round2(present),
    better: cash <= present ? ("cash" as const) : ("installments" as const),
    difference: round2(Math.abs(present - cash)),
    breakEvenDiscount: Math.round(breakEven * 10) / 10,
  };
}

/**
 * Antecipar parcelas de uma dívida ou deixar o dinheiro aplicado: compara a taxa da dívida com a
 * da aplicação. Antecipar `count` parcelas de `parcel` com desconto dos juros da dívida.
 */
export function prepay(parcel: number, count: number, debtRatePct: number, investRatePct: number, period: RatePeriod) {
  const d = toMonthly(debtRatePct, period);
  const a = toMonthly(investRatePct, period);
  // Antecipando as últimas parcelas: cada uma é paga pelo valor presente na taxa da dívida.
  let payNow = 0;
  let investedNeeded = 0;
  for (let k = 1; k <= count; k++) {
    payNow += parcel / (1 + d) ** k;
    investedNeeded += parcel / (1 + a) ** k;
  }
  return {
    payNow: round2(payNow),
    nominal: round2(parcel * count),
    discount: round2(parcel * count - payNow),
    better: d > a ? ("prepay" as const) : ("invest" as const),
    // Quanto precisaria estar aplicado hoje para pagar as mesmas parcelas no vencimento.
    investedNeeded: round2(investedNeeded),
  };
}

/** Reserva de emergência: meses de gastos essenciais (referência usual: 3 a 6; autônomos, 6 a 12). */
export function emergencyFund(monthlyEssential: number, months: number, current: number) {
  const target = monthlyEssential * months;
  return {
    target: round2(target),
    missing: round2(Math.max(0, target - current)),
    coverage: monthlyEssential > 0 ? Math.round((current / monthlyEssential) * 10) / 10 : 0,
  };
}

/** Prévia do financiamento na tela de cadastro (mesma conta do servidor, sem centavos exatos). */
export function loanPreview(
  principal: number,
  ratePct: number,
  period: RatePeriod,
  n: number,
  system: "price" | "sac",
  extras: number,
) {
  const i = toMonthly(ratePct, period);
  if (!(principal > 0) || !(n > 0)) return null;
  if (system === "price") {
    const pmt = i === 0 ? principal / n : (principal * i) / (1 - (1 + i) ** -n);
    return { first: round2(pmt + extras), last: round2(pmt + extras), interest: round2(pmt * n - principal) };
  }
  const amort = principal / n;
  const first = amort + principal * i + extras;
  const last = amort + amort * i + extras;
  const interest = (i * amort * n * (n + 1)) / 2;
  return { first: round2(first), last: round2(last), interest: round2(interest) };
}
