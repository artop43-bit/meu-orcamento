/**
 * Parcelar ou à vista › "E no meu orçamento?" (v1.6).
 *
 * Soma a parcela simulada à previsão real dos próximos meses (parcelas que a pessoa já tem,
 * fixas e gastos planejados, vindos de /analysis/projection) e mostra o efeito: quanto da renda
 * fica comprometida com parcelas, a sobra mês a mês antes e depois, o mês de menor sobra e a
 * sobra média. Sem veredito: a pessoa conclui. Também confere o limite do cartão e o saldo das
 * contas para o à vista. Só contas: nenhuma recomenda produto financeiro.
 */
import { addMonths } from "./format";

/** Um mês da previsão (valores em reais). */
export type ForecastMonth = { month: string; income: number; expenses: number; installments: number };

export type ImpactMonth = {
  month: string;
  /** Sobra prevista sem a compra (receitas − despesas). */
  before: number;
  /** Sobra com a parcela nova. */
  after: number;
};

export type Impact = {
  months: ImpactMonth[];
  /** Média mensal de parcelas que a pessoa já tem, no período da compra. */
  installmentsBefore: number;
  installmentsAfter: number;
  /** % da renda média comprometida com parcelas (null sem renda prevista). */
  committedBefore: number | null;
  committedAfter: number | null;
  /** Mês de menor sobra depois da compra. */
  worst: ImpactMonth | null;
  averageBefore: number;
  averageAfter: number;
  negativeMonths: string[];
  /** A previsão não cobre todos os meses da compra ou não tem receita: números parciais. */
  partial: boolean;
};

const round2 = (v: number) => Math.round(v * 100) / 100;
const round1 = (v: number) => Math.round(v * 10) / 10;

/** Meses (AAAA-MM) cobertos pelas parcelas, a partir do mês da 1ª. */
export function parcelMonths(firstMonth: string, count: number): string[] {
  return Array.from({ length: Math.max(0, count) }, (_, i) => addMonths(firstMonth, i));
}

export function installmentImpact(forecast: ForecastMonth[], parcel: number, count: number, firstMonth: string): Impact {
  const byMonth = new Map(forecast.map((m) => [m.month, m]));
  const window = parcelMonths(firstMonth, count);
  const known = window.map((month) => byMonth.get(month)).filter((m): m is ForecastMonth => Boolean(m));
  const months = known.map((m) => {
    const before = round2(m.income - m.expenses);
    return { month: m.month, before, after: round2(before - parcel) };
  });
  const n = known.length;
  const sum = (values: number[]) => values.reduce((a, b) => a + b, 0);
  const income = n ? sum(known.map((m) => m.income)) / n : 0;
  const installmentsBefore = n ? sum(known.map((m) => m.installments)) / n : 0;
  const installmentsAfter = installmentsBefore + (n ? parcel : 0);
  const pct = (v: number) => (income > 0 ? round1((v / income) * 100) : null);
  const worst = months.reduce<ImpactMonth | null>((low, m) => (!low || m.after < low.after ? m : low), null);
  return {
    months,
    installmentsBefore: round2(installmentsBefore),
    installmentsAfter: round2(installmentsAfter),
    committedBefore: pct(installmentsBefore),
    committedAfter: pct(installmentsAfter),
    worst,
    averageBefore: n ? round2(sum(months.map((m) => m.before)) / n) : 0,
    averageAfter: n ? round2(sum(months.map((m) => m.after)) / n) : 0,
    negativeMonths: months.filter((m) => m.after < 0).map((m) => m.month),
    partial: n < window.length || known.some((m) => m.income <= 0),
  };
}

/**
 * Menor número de parcelas (entre as opções) que mantém todos os meses da compra com sobra
 * ≥ 0. Null quando nenhuma opção consegue (ou a previsão não cobre o período).
 */
export function safestCount(forecast: ForecastMonth[], price: number, firstMonth: string, options: number[] = [1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 18, 24]): number | null {
  for (const count of [...options].sort((a, b) => a - b)) {
    const impact = installmentImpact(forecast, price / count, count, firstMonth);
    if (impact.months.length === count && impact.negativeMonths.length === 0) return count;
  }
  return null;
}

export type CardCheck = {
  /** Limite livre hoje. */
  available: number;
  /** % do limite usado depois da compra (o valor total da compra ocupa o limite). */
  usedAfterPct: number;
  /** Livre depois da compra (negativo = não cabe). */
  freeAfter: number;
  fits: boolean;
};

/** Compra parcelada no cartão: o valor TOTAL ocupa o limite e volta aos poucos, a cada parcela paga. */
export function cardCheck(limit: number, available: number, price: number): CardCheck | null {
  if (!(limit > 0)) return null;
  const freeAfter = round2(available - price);
  return { available: round2(available), freeAfter, usedAfterPct: round1(((limit - freeAfter) / limit) * 100), fits: freeAfter >= 0 };
}

export type CashCheck = { balance: number; covers: boolean; leftover: number; missing: number; reserve: number; coversWithReserve: boolean };

/**
 * À vista: o saldo das contas (o menor entre o de hoje e o previsto para o fim do mês, sem
 * vales) cobre a compra sem usar a reserva de emergência, que fica nos investimentos?
 */
export function cashCheck(balance: number, cash: number, reserve: number): CashCheck {
  const leftover = round2(balance - cash);
  return {
    balance: round2(balance),
    covers: leftover >= 0,
    leftover,
    missing: round2(Math.max(0, -leftover)),
    reserve: round2(reserve),
    coversWithReserve: leftover < 0 && balance + reserve >= cash,
  };
}

/** Lê números digitados com vírgula ou ponto ("10,5", "10.5", "1.234,56"). */
export function parseNumber(value: string): number {
  const v = (value || "").trim().replace(/\s|%/g, "");
  if (!v) return 0;
  // "1.234,56": ponto de milhar e vírgula decimal. "10.5": ponto decimal.
  const normalized = v.includes(",") ? v.replace(/\./g, "").replace(",", ".") : v;
  const n = Number(normalized);
  return Number.isFinite(n) ? n : 0;
}
