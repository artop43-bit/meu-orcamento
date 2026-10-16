const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

/** Valores chegam da API como texto ("1234.50") para não perder centavos. */
export function money(value: string | number | null | undefined): string {
  return brl.format(Number(value ?? 0));
}

/** Converte o que o usuário digitou ("1.234,50", "1234.5", "R$ 30") para "1234.50". */
export function parseMoney(input: string): string | null {
  let text = input.replace(/[R$\s]/g, "");
  if (text.includes(",")) text = text.replace(/\./g, "").replace(",", ".");
  if (!/^\d+(\.\d{1,2})?$/.test(text)) return null;
  return Number(text).toFixed(2);
}

/** Valor da API para exibir num campo editável ("1234.50" → "1234,50"). */
export function moneyInput(value: string): string {
  return Number(value).toFixed(2).replace(".", ",");
}

const MONTH_NAMES = [
  "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
  "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
];

export function monthLabel(month: string, short = false): string {
  const [year, m] = month.split("-").map(Number);
  const name = MONTH_NAMES[m - 1];
  return short ? `${name.slice(0, 3)}/${String(year).slice(2)}` : `${name} de ${year}`;
}

export function addMonths(month: string, count: number): string {
  const [year, m] = month.split("-").map(Number);
  const index = year * 12 + (m - 1) + count;
  return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, "0")}`;
}

export function thisMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

export function shortDate(iso: string | null): string {
  if (!iso) return "";
  const [, m, d] = iso.split("-");
  return `${d}/${m}`;
}

export function percent(value: number | null): string {
  return value === null ? "—" : `${value.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
}

/** Data de hoje (fuso local) no formato AAAA-MM-DD. */
export function todayISO(): string {
  const now = new Date();
  return `${thisMonth()}-${String(now.getDate()).padStart(2, "0")}`;
}
