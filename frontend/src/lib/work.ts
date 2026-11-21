import type {
  AgendaEventKind,
  AgendaEventStatus,
  AgendaLayer,
  AgendaTimelineItem,
  ProjectStatus,
  TaskPriority,
  TaskStatus,
} from "../api/work";

export const PROJECT_STATUS_LABELS: Record<ProjectStatus, string> = {
  planning: "Planejamento",
  active: "Em andamento",
  review: "Em revisão",
  done: "Concluído",
  paused: "Pausado",
};

export const TASK_STATUS_LABELS: Record<TaskStatus, string> = {
  todo: "A fazer",
  doing: "Fazendo",
  done: "Concluído",
};

export const TASK_PRIORITY_LABELS: Record<TaskPriority, string> = {
  low: "Baixa",
  medium: "Média",
  high: "Alta",
  urgent: "Urgente",
};

export const AGENDA_KIND_LABELS: Record<AgendaEventKind, string> = {
  meeting: "Reunião",
  delivery: "Entrega",
  visit: "Visita",
  reminder: "Lembrete",
  personal: "Pessoal",
};

export const AGENDA_STATUS_LABELS: Record<AgendaEventStatus, string> = {
  scheduled: "Agendado",
  confirmed: "Confirmado",
  done: "Concluído",
  cancelled: "Cancelado",
};

export const AGENDA_LAYER_META: Record<
  AgendaLayer,
  { label: string; badgeClass: string }
> = {
  agenda: { label: "Agenda", badgeClass: "badge--ok" },
  messaging: { label: "WhatsApp", badgeClass: "badge--accent" },
  crm: { label: "CRM Funil", badgeClass: "badge--muted" },
  projects: { label: "Projetos", badgeClass: "badge--warn" },
  budget: { label: "Orçamento", badgeClass: "badge--muted" },
  cofre: { label: "Cofre", badgeClass: "badge--muted" },
};

export const AGENDA_ALL_LAYERS: AgendaLayer[] = [
  "agenda",
  "messaging",
  "crm",
  "projects",
  "budget",
  "cofre",
];

export function shiftIsoDate(iso: string, deltaDays: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d + deltaDays));
  return dt.toISOString().slice(0, 10);
}

export function startOfWeekIso(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  const weekday = dt.getUTCDay(); // 0 = domingo
  dt.setUTCDate(dt.getUTCDate() - weekday);
  return dt.toISOString().slice(0, 10);
}

export function monthBoundsIso(iso: string): { start: string; end: string } {
  const [y, m] = iso.split("-").map(Number);
  const start = new Date(Date.UTC(y, m - 1, 1));
  const end = new Date(Date.UTC(y, m, 0));
  return {
    start: start.toISOString().slice(0, 10),
    end: end.toISOString().slice(0, 10),
  };
}

export function buildMonthGrid(anchorIso: string): {
  gridStart: string;
  gridEnd: string;
  monthIndex: number;
  days: { date: string; inMonth: boolean; dayNumber: number }[];
} {
  const [y, m] = anchorIso.split("-").map(Number);
  const firstDay = new Date(Date.UTC(y, m - 1, 1));
  const leading = firstDay.getUTCDay();
  const gridStart = shiftIsoDate(`${y}-${String(m).padStart(2, "0")}-01`, -leading);
  const days: { date: string; inMonth: boolean; dayNumber: number }[] = [];
  for (let i = 0; i < 42; i++) {
    const cur = shiftIsoDate(gridStart, i);
    const [, cm, cd] = cur.split("-").map(Number);
    days.push({ date: cur, inMonth: cm === m, dayNumber: cd });
  }
  return {
    gridStart,
    gridEnd: days[41]!.date,
    monthIndex: m,
    days,
  };
}

export function formatIsoDateBr(iso: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  return match ? `${match[3]}/${match[2]}/${match[1]}` : iso;
}

const shortMonth = new Intl.DateTimeFormat("pt-BR", { month: "short", timeZone: "UTC" });

export function formatAgendaPeriod(start: string, end: string): string {
  const month = (iso: string) => shortMonth.format(new Date(`${iso}T12:00:00Z`)).replace(".", "");
  const day = (iso: string) => Number(iso.slice(8));
  if (start === end) return `${day(start)} ${month(start)}`;
  if (start.slice(0, 7) === end.slice(0, 7)) return `${day(start)}–${day(end)} ${month(end)}`;
  const differentYear = start.slice(0, 4) !== end.slice(0, 4);
  const label = (iso: string) =>
    `${day(iso)} ${month(iso)}${differentYear ? ` ${iso.slice(0, 4)}` : ""}`;
  return `${label(start)} – ${label(end)}`;
}

export function groupTimelineByDay(
  items: AgendaTimelineItem[],
): { date: string; items: AgendaTimelineItem[] }[] {
  const map = new Map<string, AgendaTimelineItem[]>();
  for (const item of items) {
    const bucket = map.get(item.date);
    if (bucket) bucket.push(item);
    else map.set(item.date, [item]);
  }
  return Array.from(map.entries()).map(([date, dayItems]) => ({ date, items: dayItems }));
}

export function calcProjectProfitability(
  budgetValue: number,
  expensesTotal: number,
  totalHours: number,
): { netMargin: number; effectiveHourly: number } {
  const netMargin = Math.round((budgetValue - expensesTotal) * 100) / 100;
  const effectiveHourly = totalHours > 0 ? Math.round((netMargin / totalHours) * 100) / 100 : 0;
  return { netMargin, effectiveHourly };
}
