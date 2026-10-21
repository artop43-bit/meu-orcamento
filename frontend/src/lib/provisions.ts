import type { Planned, Recurring } from "../api/budget";
import { addMonths } from "./format";

/**
 * Provisões para gastos sazonais (v1.4): para cada gasto grande que ainda vai chegar (despesa
 * prevista no Calendário ou conta que se repete a cada 6 ou 12 meses, como IPVA, IPTU, seguro e
 * material escolar), quanto guardar por mês, a partir deste mês, para pagar sem aperto.
 */
export type Provision = {
  key: string;
  description: string;
  date: string; // AAAA-MM-DD (ou AAAA-MM-01 quando a conta não tem dia)
  amount: number;
  months: number; // meses para guardar, contando este
  perMonth: number;
};

function monthsUntil(current: string, due: string): number {
  const [y1, m1] = current.split("-").map(Number);
  const [y2, m2] = due.split("-").map(Number);
  return (y2! - y1!) * 12 + (m2! - m1!);
}

export function provisions(planned: Planned[], recurring: Recurring[], today: string, horizon = 12): Provision[] {
  const current = today.slice(0, 7);
  const out: Provision[] = [];
  for (const p of planned) {
    if (p.expense_id || p.date <= today) continue;
    const months = monthsUntil(current, p.date.slice(0, 7));
    if (months >= 1 && months <= horizon) {
      out.push({ key: `p-${p.id}`, description: p.description, date: p.date, amount: Number(p.amount), months, perMonth: Number(p.amount) / months });
    }
  }
  for (const r of recurring) {
    if (r.kind !== "expense" || (r.interval_months ?? 1) < 6) continue;
    // Próxima vez depois deste mês, respeitando o início e o fim da conta fixa.
    let next = r.start_month.slice(0, 7);
    while (next <= current) next = addMonths(next, r.interval_months);
    if (r.end_month && next > r.end_month.slice(0, 7)) continue;
    const months = monthsUntil(current, next);
    if (months < 1 || months > horizon) continue;
    const day = r.due_day ? String(r.due_day).padStart(2, "0") : "01";
    out.push({ key: `r-${r.id}`, description: r.description, date: `${next}-${day}`, amount: Number(r.amount), months, perMonth: Number(r.amount) / months });
  }
  return out.sort((a, b) => a.date.localeCompare(b.date));
}

export function totalPerMonth(list: Provision[]): number {
  return list.reduce((sum, p) => sum + p.perMonth, 0);
}
