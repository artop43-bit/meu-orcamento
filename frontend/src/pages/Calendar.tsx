import { useMemo, useState, type FormEvent, type ReactNode } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  ArrowDownLeft,
  BellRing,
  CalendarPlus,
  ChevronLeft,
  ChevronRight,
  CreditCard,
  Pencil,
  Receipt,
  Repeat,
  Trash2,
} from "lucide-react";
import { Link, useParams } from "react-router";

import {
  budgetApi,
  keys,
  useBudgetMutation,
  useCategories,
  type CalendarEvent,
  type CalendarKind,
  type Category,
  type Planned,
} from "../api/budget";
import { errorMessage } from "../api/client";
import { CategorySelect, FormActions, MoneyInput, requireMoney } from "../components/budget";
import { EmptyGuide, Tip } from "../components/help";
import { Alert, Button, LoadingRegion, PageHeader, Sheet, Skeleton } from "../components/ui";
import { announce } from "../lib/announce";
import { addMonths, money, moneyInput, monthLabel, thisMonth, todayISO } from "../lib/format";

// Cor + ícone + texto: o tipo nunca é indicado só pela cor (acessível a daltônicos).
const KINDS: Record<CalendarKind, { label: string; icon: ReactNode; className: string }> = {
  income: { label: "Renda", icon: <ArrowDownLeft size={13} />, className: "ev--income" },
  expense: { label: "Conta", icon: <Receipt size={13} />, className: "ev--expense" },
  recurring: { label: "Fixa", icon: <Repeat size={13} />, className: "ev--recurring" },
  installment: { label: "Parcela", icon: <CreditCard size={13} />, className: "ev--installment" },
  planned: { label: "Planejado", icon: <CalendarPlus size={13} />, className: "ev--planned" },
};
const WEEKDAYS = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];
const WEEKDAYS_LONG = ["domingo", "segunda", "terça", "quarta", "quinta", "sexta", "sábado"];

type Editing =
  | { type: "day"; date: string }
  | { type: "new-planned"; date: string }
  | { type: "planned"; planned: Planned }
  | null;

function useCalendar(month: string) {
  return useQuery({
    queryKey: keys.calendar(month),
    queryFn: () => budgetApi.calendar(month),
    placeholderData: keepPreviousData,
  });
}

function daysOf(month: string): string[] {
  const [y, m] = month.split("-").map(Number);
  const last = new Date(y, m, 0).getDate();
  return Array.from({ length: last }, (_, i) => `${month}-${String(i + 1).padStart(2, "0")}`);
}

function weekday(iso: string): number {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).getDay();
}

function dayLabel(iso: string): string {
  const [, m, d] = iso.split("-");
  return `${WEEKDAYS_LONG[weekday(iso)]}, ${d}/${m}`;
}

function eventStatus(e: CalendarEvent): string {
  if (e.kind === "income") return e.income_type === "variable" ? "variável" : "";
  if (e.kind === "planned") return e.paid ? "lançado" : "previsto";
  if (e.paid) return "paga";
  if (e.date && e.date < todayISO()) return "atrasada";
  return "a pagar";
}

function EventChip({ event, compact }: { event: CalendarEvent; compact?: boolean }) {
  const kind = KINDS[event.kind];
  const status = eventStatus(event);
  const sign = event.kind === "income" ? "+" : "−";
  return (
    <span className={`ev ${kind.className} ${event.paid ? "ev--done" : ""}`}>
      <span className="ev__icon" aria-hidden>
        {kind.icon}
      </span>
      <span className="ev__text">
        <span className="sr-only">{kind.label}: </span>
        {event.description}
        {event.installment_total ? ` ${event.installment_number}/${event.installment_total}` : ""}
      </span>
      {!compact && (
        <span className="ev__amount">
          {sign}
          {money(event.amount)}
        </span>
      )}
      {compact && <span className="sr-only"> {money(event.amount)}</span>}
      {status && <span className="sr-only"> ({status})</span>}
    </span>
  );
}

/** Planejados abrem para editar ou lançar; os demais só mostram. */
function EventButton({ e, compact, onOpen }: { e: CalendarEvent; compact?: boolean; onOpen: (e: CalendarEvent) => void }) {
  if (e.kind !== "planned") return <EventChip event={e} compact={compact} />;
  return (
    <button type="button" className="ev-btn" onClick={() => onOpen(e)} aria-label={`Abrir planejado ${e.description}, ${money(e.amount)}`}>
      <EventChip event={e} compact={compact} />
    </button>
  );
}

function Legend() {
  return (
    <ul className="legend" aria-label="Legenda">
      {(Object.keys(KINDS) as CalendarKind[]).map((k) => (
        <li key={k} className={`ev ${KINDS[k].className}`}>
          <span className="ev__icon" aria-hidden>
            {KINDS[k].icon}
          </span>
          {KINDS[k].label}
        </li>
      ))}
    </ul>
  );
}

// ---------------------------------------------------------------- formulário do planejado

function PlannedForm({
  categories,
  planned,
  date,
  onDone,
}: {
  categories: Category[];
  planned?: Planned;
  date: string;
  onDone: () => void;
}) {
  const [description, setDescription] = useState(planned?.description ?? "");
  const [amount, setAmount] = useState(planned ? moneyInput(planned.amount) : "");
  const [day, setDay] = useState(planned?.date ?? date);
  const [categoryId, setCategoryId] = useState(planned?.category_id ?? "");
  const [notes, setNotes] = useState(planned?.notes ?? "");
  const [error, setError] = useState("");

  const save = useBudgetMutation(async () => {
    const data = {
      description,
      amount: requireMoney(amount),
      date: day,
      category_id: categoryId || null,
      notes: notes.trim() || null,
    };
    if (planned) await budgetApi.updatePlanned(planned.id, data);
    else await budgetApi.createPlanned(data);
  });
  const confirm = useBudgetMutation((paid: boolean) => budgetApi.confirmPlanned(planned!.id, paid));
  const remove = useBudgetMutation(() => budgetApi.deletePlanned(planned!.id));

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      await save.mutateAsync(undefined);
      announce("Gasto planejado salvo");
      onDone();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function act(fn: () => Promise<unknown>, message: string) {
    setError("");
    try {
      await fn();
      announce(message);
      onDone();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  const launched = !!planned?.expense_id;
  return (
    <form className="inline-form" onSubmit={submit}>
      <Alert tone="error">{error}</Alert>
      {launched && <Alert tone="success">Já lançado como conta no mês {monthLabel(planned!.date.slice(0, 7))}.</Alert>}
      <label>
        <span className="field-label">
          O que é <Tip>Um gasto que você sabe que vai acontecer. Ex.: aniversário da mãe, IPVA, viagem de férias, material escolar.</Tip>
        </span>
        <input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Ex.: Presente de aniversário" required maxLength={120} autoFocus />
      </label>
      <div className="grid-2">
        <label>
          Valor previsto
          <MoneyInput value={amount} onChange={setAmount} placeholder="Ex.: 200,00" />
        </label>
        <label>
          Data
          <input type="date" value={day} onChange={(e) => setDay(e.target.value)} required />
        </label>
      </div>
      <label>
        Categoria
        <CategorySelect categories={categories} value={categoryId} onChange={setCategoryId} />
      </label>
      <label>
        Observação
        <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} maxLength={500} placeholder="Ex.: dividir com os irmãos" />
      </label>
      <FormActions loading={save.isPending} onCancel={onDone} label={planned ? "Salvar" : "Planejar gasto"} />
      {planned && !launched && (
        <div className="stack stack--tight" style={{ borderTop: "1px solid var(--border)", paddingTop: 16 }}>
          <p className="muted small" style={{ margin: 0 }}>
            Aconteceu? Lance como conta do mês (sai da previsão e entra no orçamento).
          </p>
          <div className="row">
            <Button type="button" loading={confirm.isPending} onClick={() => act(() => confirm.mutateAsync(true), "Lançado como conta paga")}>
              Lançar já paga
            </Button>
            <Button type="button" variant="secondary" loading={confirm.isPending} onClick={() => act(() => confirm.mutateAsync(false), "Lançado como conta a pagar")}>
              Lançar a pagar
            </Button>
          </div>
        </div>
      )}
      {planned && (
        <Button type="button" variant="danger" loading={remove.isPending} onClick={() => act(() => remove.mutateAsync(undefined), "Gasto planejado excluído")}>
          <Trash2 size={16} /> Excluir planejado
        </Button>
      )}
    </form>
  );
}

// ---------------------------------------------------------------- página

export default function CalendarPage() {
  const params = useParams();
  const month = params.month && /^\d{4}-\d{2}$/.test(params.month) ? params.month : thisMonth();
  const calendar = useCalendar(month);
  const planned = useQuery({ queryKey: ["budget", "planned", month], queryFn: () => budgetApi.planned(month) });
  const categories = useCategories();
  const [editing, setEditing] = useState<Editing>(null);
  const close = () => setEditing(null);
  const today = todayISO();
  const events = useMemo(() => calendar.data?.events ?? [], [calendar.data]);

  const byDay = useMemo(() => {
    const map = new Map<string, CalendarEvent[]>();
    for (const e of events) {
      const key = e.date ?? "sem-data";
      map.set(key, [...(map.get(key) ?? []), e]);
    }
    return map;
  }, [events]);

  const totals = useMemo(() => {
    let incoming = 0;
    let outgoing = 0;
    let plannedTotal = 0;
    for (const e of events) {
      if (e.kind === "income") incoming += Number(e.amount);
      else if (e.kind === "planned") {
        if (!e.paid) plannedTotal += Number(e.amount);
      } else outgoing += Number(e.amount);
    }
    return { incoming, outgoing, plannedTotal };
  }, [events]);

  // Lembretes: o que vence ou está previsto nos próximos 7 dias (e ainda não foi pago/lançado).
  const soon = useMemo(() => {
    const limit = new Date();
    limit.setDate(limit.getDate() + 7);
    const end = `${limit.getFullYear()}-${String(limit.getMonth() + 1).padStart(2, "0")}-${String(limit.getDate()).padStart(2, "0")}`;
    return events.filter((e) => e.kind !== "income" && !e.paid && e.date && e.date >= today && e.date <= end);
  }, [events, today]);

  const plannedById = new Map((planned.data ?? []).map((p) => [p.id, p]));
  const days = daysOf(month);
  const leading = weekday(days[0]);
  const cats = categories.data ?? [];

  function openEvent(e: CalendarEvent) {
    if (e.kind === "planned") {
      const p = plannedById.get(e.id);
      if (p) setEditing({ type: "planned", planned: p });
    }
  }

  const defaultDate = month === thisMonth() ? today : `${month}-01`;
  const title = (
    <div className="month-nav">
      <Link className="icon-btn icon-btn--bordered" to={`/calendario/${addMonths(month, -1)}`} aria-label="Mês anterior">
        <ChevronLeft size={18} />
      </Link>
      <h1>{monthLabel(month)}</h1>
      <Link className="icon-btn icon-btn--bordered" to={`/calendario/${addMonths(month, 1)}`} aria-label="Próximo mês">
        <ChevronRight size={18} />
      </Link>
    </div>
  );

  const dayEvents = editing?.type === "day" ? byDay.get(editing.date) ?? [] : [];

  return (
    <>
      <PageHeader
        title={title}
        subtitle={
          month === thisMonth() ? "Vencimentos, recebimentos e gastos planejados" : <Link to="/calendario">Voltar para o mês atual</Link>
        }
        actions={
          <Button type="button" onClick={() => setEditing({ type: "new-planned", date: defaultDate })}>
            <CalendarPlus size={16} /> Planejar gasto
          </Button>
        }
      />

      {calendar.isPending && (
        <LoadingRegion label="Carregando o calendário">
          <Skeleton height={420} />
        </LoadingRegion>
      )}
      {calendar.isError && <Alert tone="error">{errorMessage(calendar.error)}</Alert>}

      {calendar.data && (
        <div className={`stack ${calendar.isPlaceholderData ? "is-stale" : ""}`} style={{ gap: 16 }}>
          <div className="cal-summary">
            <span>
              Entradas <strong className="tone--ok">{money(totals.incoming)}</strong>
            </span>
            <span>
              Contas <strong className="tone--error">{money(totals.outgoing)}</strong>
            </span>
            <span>
              Planejados <strong>{money(totals.plannedTotal)}</strong>
              <Tip>Gastos previstos que ainda não viraram conta. Eles já entram na previsão e no consultor.</Tip>
            </span>
          </div>

          {soon.length > 0 && (
            <section className="card reminder" aria-label="Lembretes dos próximos 7 dias">
              <h2 className="row" style={{ gap: 8, fontSize: "1rem" }}>
                <BellRing size={18} /> Próximos 7 dias
              </h2>
              <ul className="agenda__list">
                {soon.map((e) => (
                  <li key={`${e.kind}-${e.id}`}>
                    <span className="muted small agenda__when">{e.date === today ? "hoje" : dayLabel(e.date!)}</span>
                    <EventButton e={e} onOpen={openEvent} />
                  </li>
                ))}
              </ul>
            </section>
          )}

          <Legend />

          {events.length === 0 && (
            <EmptyGuide
              icon={<CalendarPlus size={22} />}
              title="Nada com data neste mês"
              text="Contas com vencimento, rendas com dia de recebimento e gastos planejados aparecem aqui."
              example={<>Ex.: planeje “IPVA” R$ 1.200 em 15/03 ou “Aniversário da mãe” R$ 250 em 20/05.</>}
              action={
                <Button type="button" onClick={() => setEditing({ type: "new-planned", date: defaultDate })}>
                  <CalendarPlus size={16} /> Planejar gasto
                </Button>
              }
            />
          )}

          {/* Desktop: grade do mês. */}
          <div className="cal-grid">
            <div className="cal-grid__head" aria-hidden>
              {WEEKDAYS.map((d) => (
                <span key={d}>
                  {d}
                </span>
              ))}
            </div>
            <div className="cal-grid__days">
              {Array.from({ length: leading }, (_, i) => (
                <span key={`pad-${i}`} className="cal-day cal-day--pad" aria-hidden />
              ))}
              {days.map((iso) => {
                const list = byDay.get(iso) ?? [];
                const shown = list.slice(0, 3);
                return (
                  <div key={iso} className={`cal-day ${iso === today ? "cal-day--today" : ""}`}>
                    <button
                      type="button"
                      className="cal-day__num"
                      onClick={() => setEditing({ type: "day", date: iso })}
                      aria-label={`${dayLabel(iso)}: ${list.length ? `${list.length} item(ns)` : "nada"}. Abrir dia`}
                    >
                      {Number(iso.slice(8))}
                    </button>
                    <div className="cal-day__events">
                      {shown.map((e) => (
                        <EventButton key={`${e.kind}-${e.id}`} e={e} compact onOpen={openEvent} />
                      ))}
                      {list.length > 3 && (
                        <button type="button" className="link-btn small" onClick={() => setEditing({ type: "day", date: iso })}>
                          +{list.length - 3} mais
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {byDay.has("sem-data") && (
            <section className="card stack cal-undated" aria-label="Sem data">
              <h2 style={{ margin: 0, fontSize: "1rem" }}>Sem data neste mês</h2>
              <ul className="agenda__list">
                {byDay.get("sem-data")!.map((e) => (
                  <li key={`${e.kind}-${e.id}`}>
                    <EventButton e={e} onOpen={openEvent} />
                  </li>
                ))}
              </ul>
              <p className="muted small" style={{ margin: 0 }}>
                Dica: informe o vencimento (contas) ou o dia do recebimento (rendas) para aparecerem no dia certo.
              </p>
            </section>
          )}

          {/* Celular: agenda (lista por dia). */}
          <ol className="agenda" aria-label={`Agenda de ${monthLabel(month)}`}>
            {[...byDay.entries()].map(([key, list]) => (
              <li key={key} className={`agenda__day ${key === today ? "is-today" : ""}`}>
                <h3>{key === "sem-data" ? "Sem data" : key === today ? `Hoje · ${dayLabel(key)}` : dayLabel(key)}</h3>
                <ul className="agenda__list">
                  {list.map((e) => (
                    <li key={`${e.kind}-${e.id}`}>
                      <EventButton e={e} onOpen={openEvent} />
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ol>
        </div>
      )}

      <Sheet open={editing?.type === "day"} title={editing?.type === "day" ? dayLabel(editing.date) : ""} onClose={close}>
        {editing?.type === "day" && (
          <div className="stack">
            {dayEvents.length === 0 ? (
              <p className="muted" style={{ margin: 0 }}>
                Nada neste dia.
              </p>
            ) : (
              <ul className="agenda__list">
                {dayEvents.map((e) => (
                  <li key={`${e.kind}-${e.id}`}>
                    <EventButton e={e} onOpen={openEvent} />
                  </li>
                ))}
              </ul>
            )}
            <div className="row">
              <Button type="button" onClick={() => setEditing({ type: "new-planned", date: editing.date })}>
                <CalendarPlus size={16} /> Planejar gasto neste dia
              </Button>
              <Link className="btn btn--secondary" to={`/orcamento/${month}`}>
                <Pencil size={16} /> Ver contas do mês
              </Link>
            </div>
          </div>
        )}
      </Sheet>
      <Sheet open={editing?.type === "new-planned"} title="Planejar gasto" onClose={close}>
        {editing?.type === "new-planned" && <PlannedForm categories={cats} date={editing.date} onDone={close} />}
      </Sheet>
      <Sheet open={editing?.type === "planned"} title="Gasto planejado" onClose={close}>
        {editing?.type === "planned" && <PlannedForm categories={cats} planned={editing.planned} date={editing.planned.date} onDone={close} />}
      </Sheet>
    </>
  );
}
