import { getPrefs } from "./prefs";

const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

/** Valores chegam da API como texto ("1234.50") para não perder centavos. */
export function money(value: string | number | null | undefined): string {
  // Modo privacidade: a tela mostra só "R$ ••••" (o leitor de tela também).
  if (getPrefs().privacy) return "R$ ••••";
  return brl.format(Number(value ?? 0));
}

/** Textos prontos (ex.: do consultor) com valores dentro: no modo privacidade, os valores somem. */
export function maskMoney(text: string): string {
  return getPrefs().privacy ? text.replace(/-?R\$\s?-?[\d.]+(,\d{2})?/g, "R$ ••••") : text;
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

let cycleStart = 1;

/** Dia em que começa o mês financeiro da conta (1 = mês do calendário). */
export function setCycleStart(day: number) {
  cycleStart = day >= 1 && day <= 28 ? day : 1;
}

export function getCycleStart(): number {
  return cycleStart;
}

/** Mês do orçamento de hoje: com o mês começando no dia 5, o dia 2/11 ainda é "outubro". */
export function thisMonth(): string {
  const now = new Date();
  const ref = now.getDate() < cycleStart ? new Date(now.getFullYear(), now.getMonth() - 1, 1) : now;
  return `${ref.getFullYear()}-${String(ref.getMonth() + 1).padStart(2, "0")}`;
}

/** Período do mês financeiro (ex.: "5/10 a 4/11"); vazio quando o mês é o do calendário. */
export function cycleLabel(month: string): string {
  if (cycleStart === 1) return "";
  const [y, m] = month.split("-").map(Number);
  const start = new Date(y!, m! - 1, Math.min(cycleStart, new Date(y!, m!, 0).getDate()));
  const nextStart = new Date(y!, m!, Math.min(cycleStart, new Date(y!, m! + 1, 0).getDate()));
  const end = new Date(nextStart.getTime() - 86_400_000);
  const fmt = (d: Date) => `${d.getDate()}/${d.getMonth() + 1}`;
  return `${fmt(start)} a ${fmt(end)}`;
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
