import { useQuery } from "@tanstack/react-query";
import { ArrowDownLeft, CalendarClock } from "lucide-react";
import { Link } from "react-router";

import { periodsApi, type Periods } from "../api/analysis";
import { useMe } from "../api/auth";
import type { MonthData } from "../api/budget";
import { insightsApi } from "../api/insights";
import { useProfile } from "../api/profile";
import { addMonths, money, monthLabel, shortDate } from "../lib/format";

/* Peças do painel do Orçamento (v1.7.5): saudação com o resumo numa frase, mini gráficos de
   tendência, gastos por período e a linha do mês. */

const DAY = 86_400_000;

function iso(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function parse(value: string): Date {
  const [y, m, d] = value.split("-").map(Number);
  return new Date(y!, m! - 1, d!);
}

/** Primeiro e último dia do mês financeiro (começa no dia `startDay`). */
export function cycleRange(month: string, startDay: number): [Date, Date] {
  const [y, m] = month.split("-").map(Number);
  const clamp = (year: number, monthIndex: number) => Math.min(startDay, new Date(year, monthIndex + 1, 0).getDate());
  const start = new Date(y!, m! - 1, clamp(y!, m! - 1));
  const next = new Date(y!, m!, clamp(y!, m!));
  return [start, new Date(next.getTime() - DAY)];
}

export function usePeriods(month: string) {
  return useQuery({ queryKey: ["budget", "periods", month], queryFn: () => periodsApi.get(month) });
}

export function useSixMonths(month: string) {
  return useQuery({ queryKey: ["budget", "trends6", month], queryFn: () => insightsApi.trends(month, 6), staleTime: 60_000 });
}

// ---------------------------------------------------------------- mini gráfico

/** Linha pequena de tendência (decorativa: o valor e o rótulo ficam ao lado). */
export function Spark({ values, tone = "accent" }: { values: number[]; tone?: "accent" | "expense" | "warn" }) {
  const clean = values.filter((v) => Number.isFinite(v));
  if (clean.length < 2 || clean.every((v) => v === clean[0])) return null;
  const max = Math.max(...clean);
  const min = Math.min(...clean);
  const x = (i: number) => (i / (clean.length - 1)) * 60 + 2;
  const y = (v: number) => 20 - ((v - min) / (max - min || 1)) * 16;
  const path = clean.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(" ");
  return (
    <svg className={`spark spark--${tone}`} width="64" height="24" viewBox="0 0 64 24" fill="none" aria-hidden>
      <path d={path} pathLength={1} />
      <circle cx={x(clean.length - 1)} cy={y(clean.at(-1)!)} r="2.6" />
    </svg>
  );
}

// ---------------------------------------------------------------- saudação

export type Greeting = { hello: string; parts: string[] };

/** Monta a frase do topo com o que importa agora (pura, para testar). */
export function greeting(data: MonthData, today: string, hour: number, name: string | null, range: [Date, Date]): Greeting {
  const hello = `${hour < 12 ? "Bom dia" : hour < 18 ? "Boa tarde" : "Boa noite"}${name ? `, ${name}` : ""}`;
  const parts: string[] = [];
  const balance = Number(data.summary.balance);
  if (data.incomes.length || data.expenses.length) {
    parts.push(balance < 0 ? `O mês está ${money(Math.abs(balance))} no negativo.` : `Sobram ${money(balance)} neste mês.`);
  }
  const now = parse(today);
  const week = iso(new Date(now.getTime() + 7 * DAY));
  const unpaid = data.expenses.filter((e) => !e.paid && e.due_date);
  const late = unpaid.filter((e) => e.due_date! < today);
  const soon = unpaid.filter((e) => e.due_date! >= today && e.due_date! <= week);
  if (late.length) parts.push(`${late.length} conta(s) em atraso.`);
  if (soon.length) {
    const total = soon.reduce((sum, e) => sum + Number(e.amount), 0);
    parts.push(`${soon.length === 1 ? "1 conta vence" : `${soon.length} contas vencem`} nos próximos 7 dias (${money(total)}).`);
  }
  const incomes = data.incomes
    .filter((i) => i.day)
    .map((i) => ({ income: i, date: incomeDate(i.day!, range) }))
    .filter((i) => iso(i.date) > today)
    .sort((a, b) => a.date.getTime() - b.date.getTime());
  if (incomes[0]) {
    const days = Math.round((incomes[0].date.getTime() - now.getTime()) / DAY);
    parts.push(`${incomes[0].income.description} cai ${days === 1 ? "amanhã" : `em ${days} dias`}.`);
  }
  if (parts.length === 0) parts.push("Comece lançando as receitas e as despesas do mês.");
  return { hello, parts: parts.slice(0, 3) };
}

function incomeDate(day: number, [start, end]: [Date, Date]): Date {
  // O dia cai no mês do início do ciclo ou, se for antes do início, no mês seguinte.
  const first = new Date(start.getFullYear(), start.getMonth(), Math.min(day, new Date(start.getFullYear(), start.getMonth() + 1, 0).getDate()));
  if (first >= start && first <= end) return first;
  return new Date(end.getFullYear(), end.getMonth(), Math.min(day, new Date(end.getFullYear(), end.getMonth() + 1, 0).getDate()));
}

export function MonthGreeting({ data, month }: { data: MonthData; month: string }) {
  const me = useMe();
  const profile = useProfile();
  const range = cycleRange(month, me.data?.month_start_day ?? 1);
  const now = new Date();
  const name = profile.data?.display_name?.trim().split(/\s+/)[0] ?? null;
  const { hello, parts } = greeting(data, iso(now), now.getHours(), name, range);
  const date = now.toLocaleDateString("pt-BR", { weekday: "long", day: "numeric", month: "long" });
  return (
    <section className="greeting" aria-label="Resumo de agora">
      <span className="greeting__date">
        <CalendarClock size={14} aria-hidden /> {date.charAt(0).toUpperCase() + date.slice(1)}
      </span>
      <h2 className="greeting__hello">{hello}</h2>
      <p className="greeting__text">{parts.join(" ")}</p>
    </section>
  );
}

// ---------------------------------------------------------------- gastos por período

export function PeriodPills({ periods, month, current }: { periods: Periods | undefined; month: string; current: boolean }) {
  if (!periods) return null;
  const items: [string, string][] = current
    ? [
        ["Hoje", periods.today],
        ["Esta semana", periods.week],
        ["Este mês", periods.month],
        ["Este ano", periods.year],
      ]
    : [
        ["No mês", periods.month],
        ["No ano até aqui", periods.year],
      ];
  return (
    <dl className="period-pills" aria-label="Gastos por período">
      {items.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{money(value)}</dd>
        </div>
      ))}
      <PeriodDelta periods={periods} month={month} />
    </dl>
  );
}

function PeriodDelta({ periods, month }: { periods: Periods; month: string }) {
  const before = Number(periods.previous_same_days);
  const now = Number(periods.month);
  if (before <= 0 || now === before) return null;
  const diff = now - before;
  const previous = monthLabel(addMonths(month, -1)).split(" ")[0]!.toLowerCase();
  return (
    <div className={`period-pills__delta ${diff > 0 ? "is-up" : "is-down"}`}>
      <dt className="sr-only">Comparado ao mês anterior</dt>
      <dd>
        {diff > 0 ? "▲" : "▼"} {money(Math.abs(diff))} {diff > 0 ? "a mais" : "a menos"} que no mesmo trecho de {previous}
      </dd>
    </div>
  );
}

// ---------------------------------------------------------------- linha do mês

export type Stop = { date: string; pos: number; label: string; amount: number; count: number; kind: "income" | "paid" | "late" | "next" };

/** Paradas da linha do mês: receitas com dia e vencimentos, agrupando o que cai perto (pura). */
export function monthStops(data: MonthData, today: string, [start, end]: [Date, Date], gap = 12, max = 8): Stop[] {
  const span = Math.max(1, (end.getTime() - start.getTime()) / DAY);
  const pos = (date: Date) => Math.min(100, Math.max(0, ((date.getTime() - start.getTime()) / DAY / span) * 100));
  const raw: Stop[] = [];
  for (const income of data.incomes) {
    if (!income.day) continue;
    const date = incomeDate(income.day, [start, end]);
    raw.push({ date: iso(date), pos: pos(date), label: income.description, amount: Number(income.amount), count: 1, kind: "income" });
  }
  const byDate = new Map<string, Stop>();
  for (const expense of data.expenses) {
    if (!expense.due_date) continue;
    const date = parse(expense.due_date);
    if (date < start || date > end) continue;
    const kind: Stop["kind"] = expense.paid ? "paid" : expense.due_date < today ? "late" : "next";
    const key = `${expense.due_date}|${kind}`;
    const stop = byDate.get(key);
    if (stop) {
      stop.amount += Number(expense.amount);
      stop.count += 1;
      stop.label = `${stop.count} contas`;
    } else byDate.set(key, { date: expense.due_date, pos: pos(date), label: expense.description, amount: Number(expense.amount), count: 1, kind });
  }
  raw.push(...byDate.values());
  // Cabem poucas paradas: ficam as que pedem atenção e as maiores.
  const weight = (s: Stop) => (s.kind === "late" ? 4 : s.kind === "next" ? 3 : s.kind === "income" ? 2 : 1) * 1e9 + s.amount;
  const kept = [...raw].sort((a, b) => weight(b) - weight(a)).slice(0, max * 2).sort((a, b) => a.pos - b.pos || a.kind.localeCompare(b.kind));
  // Receitas ficam acima da linha e contas abaixo: cada lado agrupa o que cai perto.
  const rank = { late: 3, next: 2, paid: 1, income: 0 } as const;
  const merged: Stop[] = [];
  for (const side of [kept.filter((s) => s.kind === "income"), kept.filter((s) => s.kind !== "income")]) {
    let last: Stop | undefined;
    for (const stop of side) {
      if (last && stop.pos - last.pos < gap) {
        last.amount += stop.amount;
        last.count += stop.count;
        last.label = last.kind === "income" ? `${last.count} receitas` : `${last.count} contas`;
        if (rank[stop.kind] > rank[last.kind]) last.kind = stop.kind;
      } else {
        last = { ...stop };
        merged.push(last);
      }
    }
  }
  return merged.sort((a, b) => weight(b) - weight(a)).slice(0, max).sort((a, b) => a.pos - b.pos);
}

const STOP_TEXT: Record<Stop["kind"], string> = { income: "receita", paid: "paga", late: "atrasada", next: "a vencer" };

export function MonthLine({ data, month }: { data: MonthData; month: string }) {
  const me = useMe();
  const range = cycleRange(month, me.data?.month_start_day ?? 1);
  const today = iso(new Date());
  const stops = monthStops(data, today, range);
  if (stops.length === 0) return null;
  const [start, end] = range;
  const now = parse(today);
  const span = Math.max(1, (end.getTime() - start.getTime()) / DAY);
  const progress = now < start ? 0 : now > end ? 100 : ((now.getTime() - start.getTime()) / DAY / span) * 100;
  const inMonth = now >= start && now <= end;
  return (
    <section className="card month-line" aria-labelledby="linha-do-mes">
      <div className="month-line__head">
        <h2 id="linha-do-mes">Linha do mês</h2>
        <Link to={`/calendario/${month}`} className="small">
          Ver o calendário
        </Link>
      </div>
      <div className="month-line__scroll" tabIndex={0} role="group" aria-label="Receitas e vencimentos ao longo do mês">
        <ol className="month-line__track" style={{ "--progress": `${progress}%` } as React.CSSProperties}>
          <li className="month-line__fill" aria-hidden />
          {inMonth && (
            <li className="month-line__today" aria-label={`Hoje, ${shortDate(today)}`}>
              <span className="month-line__marker" aria-hidden>
                hoje
              </span>
            </li>
          )}
          {stops.map((stop) => (
            <li key={`${stop.date}-${stop.kind}`} className={`month-line__stop month-line__stop--${stop.kind}`} style={{ left: `${stop.pos}%` }}>
              <span className="month-line__dot" aria-hidden>
                {stop.kind === "income" && <ArrowDownLeft size={10} />}
              </span>
              <span className="month-line__label">{stop.label}</span>
              <span className="month-line__meta">
                {shortDate(stop.date)} · {money(stop.amount)}
                <span className="sr-only"> ({STOP_TEXT[stop.kind]})</span>
              </span>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- anel essencial × não essencial

export function EssentialRing({ essential, total }: { essential: number; total: number }) {
  if (total <= 0) return null;
  const pct = Math.round((essential / total) * 100);
  const circumference = 2 * Math.PI * 15;
  return (
    <div className="ring" role="img" aria-label={`${pct}% do gasto é essencial e ${100 - pct}% não essencial`}>
      <svg viewBox="0 0 36 36" aria-hidden>
        <circle className="ring__track" cx="18" cy="18" r="15" />
        <circle className="ring__value" cx="18" cy="18" r="15" strokeDasharray={`${(pct / 100) * circumference} ${circumference}`} transform="rotate(-90 18 18)" />
      </svg>
      <span className="ring__text">
        <strong>{pct}%</strong>
        <span>essencial</span>
      </span>
    </div>
  );
}

// ---------------------------------------------------------------- trilha da meta

/** Trilha da meta (v1.7.5): marcos em 25, 50, 75 e 100% e um marcador que anda até onde chegou. */
export function GoalTrack({ pct }: { pct: number }) {
  const value = Math.max(0, Math.min(100, pct));
  return (
    <div
      className="goal-track"
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(value)}
      aria-label="Progresso da meta"
      style={{ "--progress": `${value}%` } as React.CSSProperties}
    >
      <span className="goal-track__fill" />
      {[25, 50, 75, 100].map((mark) => (
        <span key={mark} className={`goal-track__mark ${value >= mark ? "is-done" : ""}`} style={{ left: `${mark}%` }}>
          <span className="goal-track__dot" />
          <span className="goal-track__label">{mark}%</span>
        </span>
      ))}
      <span className="goal-track__marker" aria-hidden />
    </div>
  );
}
