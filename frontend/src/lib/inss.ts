/**
 * Desconto do INSS de quem tem carteira assinada (empregado, doméstico e avulso), pela tabela
 * progressiva: cada faixa do salário paga a própria alíquota, até o teto.
 * Tabela de 2026: Portaria Interministerial MPS/MF nº 13, de 9/1/2026 (gov.br/inss).
 */
export const INSS_YEAR = 2026;

/** [limite da faixa, alíquota]. */
const BRACKETS: [number, number][] = [
  [1621.0, 0.075],
  [2902.84, 0.09],
  [4354.27, 0.12],
  [8475.55, 0.14],
];

/** Arredonda para centavos sem o erro do ponto flutuante (121,575 → 121,58). */
function cents(value: number): number {
  return Math.round(Number((value * 100).toFixed(6))) / 100;
}

export type InssResult = { gross: number; inss: number; net: number; rate: number };

/** Salário bruto → desconto do INSS, líquido (antes de IR e outros descontos) e alíquota efetiva. */
export function inssDiscount(gross: number): InssResult {
  let inss = 0;
  let floor = 0;
  for (const [ceiling, rate] of BRACKETS) {
    if (gross <= floor) break;
    inss += (Math.min(gross, ceiling) - floor) * rate;
    floor = ceiling;
  }
  inss = cents(inss);
  const net = cents(gross - inss);
  return { gross, inss, net, rate: gross > 0 ? inss / gross : 0 };
}
