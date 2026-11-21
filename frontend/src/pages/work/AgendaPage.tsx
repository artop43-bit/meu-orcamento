import { useMemo, useState, type ReactNode } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  BellRing,
  CalendarCheck,
  CalendarDays,
  CalendarPlus,
  Check,
  ChevronLeft,
  ChevronRight,
  FolderKanban,
  Handshake,
  MapPin,
  MessageCircle,
  Plus,
  Receipt,
  ShieldCheck,
  Trash2,
} from "lucide-react";

import { errorMessage } from "../../api/client";
import {
  agendaApi,
  useAgendaBridges,
  useAgendaTimeline,
  type AgendaEventStatus,
  type AgendaLayer,
  type AgendaTimelineItem,
} from "../../api/work";
import { Badge } from "../../components/budget";
import { EmptyGuide } from "../../components/help";
import { Alert, Button, LoadingRegion, PageHeader, Sheet, Skeleton } from "../../components/ui";
import { useUndo } from "../../components/undo";
import { AgendaEventSheet } from "../../components/work/AgendaEventSheet";
import { WhatsappConfirmSheet } from "../../components/work/WhatsappConfirmSheet";
import { formatDateHeading, plural, todayISO } from "../../lib/format";
import {
  AGENDA_ALL_LAYERS,
  AGENDA_LAYER_META,
  AGENDA_STATUS_LABELS,
  buildMonthGrid,
  formatAgendaPeriod,
  formatIsoDateBr,
  groupTimelineByDay,
  monthBoundsIso,
  shiftIsoDate,
  startOfWeekIso,
} from "../../lib/work";

type ViewMode = "day" | "week" | "month" | "list";

const LAYER_STYLES: Record<AgendaLayer, { className: string; swatch: string; icon: ReactNode }> = {
  agenda: { className: "ev--agenda", swatch: "swatch--agenda", icon: <CalendarCheck size={12} /> },
  messaging: { className: "ev--messaging", swatch: "swatch--messaging", icon: <MessageCircle size={12} /> },
  crm: { className: "ev--crm", swatch: "swatch--crm", icon: <Handshake size={12} /> },
  projects: { className: "ev--projects", swatch: "swatch--projects", icon: <FolderKanban size={12} /> },
  budget: { className: "ev--budget", swatch: "swatch--budget", icon: <Receipt size={12} /> },
  cofre: { className: "ev--cofre", swatch: "swatch--cofre", icon: <ShieldCheck size={12} /> },
};

const WEEKDAYS = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];

function dayLongLabel(iso: string, today: string): string {
  if (iso === today) return `Hoje · ${formatIsoDateBr(iso)}`;
  const [y, m, d] = iso.split("-").map(Number);
  const weekday = new Date(y!, m! - 1, d!).toLocaleDateString("pt-BR", { weekday: "long" });
  return `${weekday}, ${formatIsoDateBr(iso)}`;
}

function EventPill({ item, today }: { item: AgendaTimelineItem; today: string }) {
  const style = LAYER_STYLES[item.layer];
  const isDone = item.status === "done" || item.status === "completed";
  const isOverdue = item.layer === "budget" && item.status === "open" && item.date < today;
  return (
    <span className={`ev ${style.className}${isDone ? " ev--done" : ""}${isOverdue ? " ev--overdue" : ""}`}>
      <span className="ev__icon" aria-hidden>
        {style.icon}
      </span>
      <span className="ev__text">
        {item.time ? `${item.time} · ` : ""}
        {item.title}
      </span>
    </span>
  );
}

export default function AgendaPage() {
  const qc = useQueryClient();
  const undo = useUndo();
  const [view, setView] = useState<ViewMode>("week");
  const [anchorDate, setAnchorDate] = useState(() => todayISO());
  const [layers, setLayers] = useState<AgendaLayer[]>(() => [...AGENDA_ALL_LAYERS]);
  const [dayModalDate, setDayModalDate] = useState<string | null>(null);

  const today = todayISO();

  const range = useMemo(() => {
    if (view === "day") return { start: anchorDate, end: anchorDate };
    if (view === "week") {
      const start = startOfWeekIso(anchorDate);
      return { start, end: shiftIsoDate(start, 6) };
    }
    if (view === "month") return monthBoundsIso(anchorDate);
    return { start: anchorDate, end: shiftIsoDate(anchorDate, 30) };
  }, [anchorDate, view]);

  const timelineQuery = useAgendaTimeline(range.start, range.end, layers);
  const items = useMemo(
    () =>
      (timelineQuery.data?.items ?? []).filter(
        (it) => !(it.layer === "agenda" && undo.isHidden(it.id)),
      ),
    [timelineQuery.data, undo],
  );
  const counts = timelineQuery.data?.counts_by_layer;
  const dayGroups = useMemo(() => groupTimelineByDay(items), [items]);
  const monthGrid = useMemo(() => buildMonthGrid(anchorDate), [anchorDate]);

  const soonWindowEnd = shiftIsoDate(today, 7);
  const soonQuery = useAgendaTimeline(today, soonWindowEnd, layers);
  const soonItems = useMemo(
    () =>
      (soonQuery.data?.items ?? []).filter(
        (it) =>
          it.status !== "done" &&
          it.status !== "cancelled" &&
          !(it.layer === "agenda" && undo.isHidden(it.id)),
      ),
    [soonQuery.data, undo],
  );
  const todayItemsCount = useMemo(
    () => (soonQuery.data?.items ?? []).filter((it) => it.date === today).length,
    [soonQuery.data, today],
  );
  const tomorrow = shiftIsoDate(today, 1);
  const tomorrowCount = soonItems.filter((item) => item.date === tomorrow).length;

  const [eventOpen, setEventOpen] = useState(false);
  const [eventDefaultDate, setEventDefaultDate] = useState(() => todayISO());

  const [confirmItem, setConfirmItem] = useState<AgendaTimelineItem | null>(null);
  const [confirmText, setConfirmText] = useState("");
  const [confirmChatName, setConfirmChatName] = useState<string | null>(null);
  const [confirmHasChat, setConfirmHasChat] = useState(false);

  const [feedback, setFeedback] = useState<string | null>(null);
  const bridges = useAgendaBridges(eventOpen).data;

  function invalidateAgenda() {
    void qc.invalidateQueries({ queryKey: ["agenda"] });
  }

  function toggleLayer(layer: AgendaLayer) {
    setLayers((prev) =>
      prev.includes(layer) ? prev.filter((l) => l !== layer) : [...prev, layer],
    );
  }

  function shiftPeriod(dir: -1 | 1) {
    if (view === "day") setAnchorDate((d) => shiftIsoDate(d, dir));
    else if (view === "week") setAnchorDate((d) => shiftIsoDate(d, dir * 7));
    else if (view === "month") setAnchorDate((d) => shiftIsoDate(d, dir * 30));
    else setAnchorDate((d) => shiftIsoDate(d, dir * 14));
  }

  function openNewEvent(defaultDate?: string) {
    setEventDefaultDate(defaultDate ?? anchorDate);
    setEventOpen(true);
  }

  const updateEventStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: AgendaEventStatus }) =>
      agendaApi.updateEvent(id, { status }),
    onSuccess: () => invalidateAgenda(),
  });

  function deleteEventWithUndo(item: AgendaTimelineItem) {
    undo.remove({
      ids: [item.id],
      message: `${item.title} excluído`,
      commit: async () => {
        await agendaApi.deleteEvent(item.id);
        invalidateAgenda();
      },
    });
  }

  const prepareWhatsapp = useMutation({
    mutationFn: (item: AgendaTimelineItem) =>
      agendaApi.confirmWhatsapp(item.id, { send_now: false }),
    onSuccess: (res, item) => {
      setConfirmItem(item);
      setConfirmText(res.text);
      setConfirmChatName(res.chat_name);
      setConfirmHasChat(Boolean(res.chat_id));
    },
    onError: (e) => setFeedback(errorMessage(e)),
  });

  const dayModalEvents = dayModalDate ? items.filter((it) => it.date === dayModalDate) : [];

  function renderTimelineRow(item: AgendaTimelineItem) {
    return (
      <li key={item.uid}>
        <article className="split agenda-row__article">
          <div className="stack stack--tight agenda-row__main">
            <EventPill item={item} today={today} />
            <div className="row row--tight muted small">
              <Badge
                tone={
                  item.layer === "agenda" || item.layer === "messaging"
                    ? "accent"
                    : item.layer === "projects"
                      ? "warn"
                      : "neutral"
                }
              >
                {AGENDA_LAYER_META[item.layer].label}
              </Badge>
              {item.layer === "agenda" && AGENDA_STATUS_LABELS[item.status as AgendaEventStatus] && (
                <span>{AGENDA_STATUS_LABELS[item.status as AgendaEventStatus]}</span>
              )}
              {item.subtitle && <span>· {item.subtitle}</span>}
              {item.location && (
                <span className="row row--tight">
                  · <MapPin size={12} aria-hidden /> {item.location}
                </span>
              )}
              {item.notes && <span>· {item.notes}</span>}
            </div>
          </div>

          {item.layer === "agenda" && (
            <div className="row row--tight">
              <button
                type="button"
                className="btn btn--secondary btn--sm"
                onClick={() => prepareWhatsapp.mutate(item)}
              >
                <MessageCircle size={13} /> Confirmar WhatsApp
              </button>
              {item.status !== "done" && (
                <button
                  type="button"
                  className="btn btn--secondary btn--sm"
                  onClick={() => updateEventStatus.mutate({ id: item.id, status: "done" })}
                >
                  <Check size={13} /> Concluir
                </button>
              )}
              <button
                type="button"
                className="icon-btn icon-btn--bordered"
                aria-label={`Excluir ${item.title}`}
                onClick={() => deleteEventWithUndo(item)}
              >
                <Trash2 size={13} />
              </button>
            </div>
          )}
        </article>
      </li>
    );
  }

  return (
    <div className="stack">
      <PageHeader
        title="Agenda"
        subtitle="Compromissos, WhatsApp, CRM, Projetos, Cofre e Orçamento numa linha do tempo única."
        actions={
          <Button type="button" onClick={() => openNewEvent()}>
            <Plus size={16} /> Novo compromisso
          </Button>
        }
      />

      {feedback && (
        <Alert tone="info">
          <div className="split">
            <span>{feedback}</span>
            <button type="button" className="btn btn--secondary btn--sm" onClick={() => setFeedback(null)}>
              Fechar
            </button>
          </div>
        </Alert>
      )}

      <div className="greeting">
        <span className="greeting__date">{formatDateHeading()}</span>
        <p className="greeting__hello">
          {todayItemsCount > 0
            ? `Hoje você tem ${todayItemsCount} ${plural(todayItemsCount, "evento", "eventos")} na agenda.`
            : tomorrowCount > 0
              ? `Hoje está livre. Você tem ${tomorrowCount} ${plural(tomorrowCount, "evento", "eventos")} amanhã.`
              : "Hoje está livre."}
        </p>
        <p className="greeting__text">
          {soonItems.length > 0
            ? `${soonItems.length} ${plural(soonItems.length, "evento pendente", "eventos pendentes")} nos próximos 7 dias.`
            : "Nenhum compromisso ou vencimento pendente para os próximos 7 dias."}
        </p>
      </div>

      <div className="cal-summary">
        <span>
          No período <strong className="tone--ok">{items.length}</strong> {plural(items.length, "evento", "eventos")}
        </span>
        <span>
          Agenda <strong>{counts?.agenda ?? 0}</strong>
        </span>
        <span>
          WhatsApp <strong>{counts?.messaging ?? 0}</strong>
        </span>
        <span>
          CRM Funil <strong>{counts?.crm ?? 0}</strong>
        </span>
        <span>
          Projetos <strong>{counts?.projects ?? 0}</strong>
        </span>
        <span>
          Cofre <strong>{counts?.cofre ?? 0}</strong>
        </span>
        <span>
          Orçamento <strong>{counts?.budget ?? 0}</strong>
        </span>
      </div>

      {soonItems.length > 0 && (
        <section className="card reminder" aria-label="Lembretes dos próximos 7 dias">
          <h2 className="row reminder__title">
            <BellRing size={18} /> Próximos 7 dias
          </h2>
          <ul className="agenda__list">
            {soonItems.slice(0, 5).map((item) => (
              <li key={`soon-${item.uid}`}>
                <span className="muted small agenda__when">
                  {item.date === today ? "hoje" : formatIsoDateBr(item.date)}
                </span>
                <EventPill item={item} today={today} />
                <Badge tone="neutral">{AGENDA_LAYER_META[item.layer].label}</Badge>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="stack stack--tight">
        <div className="split agenda-controls">
          <div className="month-nav agenda-period">
            <button
              type="button"
              className="icon-btn icon-btn--bordered"
              aria-label="Período anterior"
              onClick={() => shiftPeriod(-1)}
            >
              <ChevronLeft size={16} />
            </button>
            <strong className="agenda-period__full">
              {formatIsoDateBr(range.start)} — {formatIsoDateBr(range.end)}
            </strong>
            <strong className="agenda-period__short" title={`${formatIsoDateBr(range.start)} — ${formatIsoDateBr(range.end)}`}>
              {formatAgendaPeriod(range.start, range.end)}
            </strong>
            <button
              type="button"
              className="icon-btn icon-btn--bordered"
              aria-label="Próximo período"
              onClick={() => shiftPeriod(1)}
            >
              <ChevronRight size={16} />
            </button>
            <button
              type="button"
              className="chip-btn"
              onClick={() => setAnchorDate(today)}
            >
              Hoje
            </button>
          </div>

          <div
            className="agenda-view-scroll"
            role="region"
            aria-label="Visualização da agenda"
            tabIndex={0}
          >
            <div className="segmented agenda-view" role="tablist" aria-label="Modo de visualização">
              {(
                [
                  ["day", "Dia"],
                  ["week", "Semana"],
                  ["month", "Mês"],
                  ["list", "Próximos"],
                ] as [ViewMode, string][]
              ).map(([mode, label]) => (
                <button
                  key={mode}
                  type="button"
                  role="tab"
                  aria-selected={view === mode}
                  className={view === mode ? "is-active" : ""}
                  onClick={() => setView(mode)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div
          className="list-tools list-tools--pills agenda-layer-tools"
          role="region"
          aria-label="Camadas da agenda"
          tabIndex={0}
        >
          <div className="pill-group agenda-layers" role="group" aria-label="Filtrar camadas da agenda">
            {AGENDA_ALL_LAYERS.map((layer) => {
              const active = layers.includes(layer);
              const meta = AGENDA_LAYER_META[layer];
              return (
                <button
                  key={layer}
                  type="button"
                  className="chip-btn"
                  aria-pressed={active}
                  onClick={() => toggleLayer(layer)}
                >
                  <span className={`swatch ${LAYER_STYLES[layer].swatch}`} aria-hidden />
                  {meta.label} ({counts?.[layer] ?? 0})
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {timelineQuery.isPending && (
        <LoadingRegion label="Carregando linha do tempo">
          <Skeleton height={240} />
        </LoadingRegion>
      )}
      {timelineQuery.isError && <Alert tone="error">{errorMessage(timelineQuery.error)}</Alert>}

      {!timelineQuery.isPending && items.length === 0 && view !== "month" && (
        <section className="card">
          <EmptyGuide
            icon={<CalendarDays size={22} />}
            title="Nenhum evento nesta janela"
            text="Crie um compromisso ou escolha quais soluções quer ver na agenda."
            example={<>Ex.: “Reunião de Kickoff” amanhã às 09:00 com confirmação em 1 toque no WhatsApp.</>}
            action={
              <Button type="button" onClick={() => openNewEvent()}>
                <Plus size={16} /> Novo compromisso
              </Button>
            }
          />
        </section>
      )}

      {!timelineQuery.isPending && view === "month" && (
        <>
          <div className="cal-grid">
            <div className="cal-grid__head" aria-hidden>
              {WEEKDAYS.map((wd) => (
                <span key={wd}>{wd}</span>
              ))}
            </div>
            <div className="cal-grid__days">
              {monthGrid.days.map((cell) => {
                const dayEvents = items.filter((it) => it.date === cell.date);
                return (
                  <div
                    key={cell.date}
                    className={`cal-day ${!cell.inMonth ? "cal-day--pad" : ""} ${
                      cell.date === today ? "cal-day--today" : ""
                    }`}
                  >
                    <button
                      type="button"
                      className="cal-day__num"
                      onClick={() => setDayModalDate(cell.date)}
                    >
                      {cell.dayNumber}
                      <span className="sr-only">
                        , {formatIsoDateBr(cell.date)}: {dayEvents.length} {plural(dayEvents.length, "evento", "eventos")}. Abrir dia
                      </span>
                    </button>
                    <div className="cal-day__events">
                      {dayEvents.slice(0, 3).map((ev) => (
                        <button
                          key={ev.uid}
                          type="button"
                          className="ev-btn"
                          onClick={() => setDayModalDate(cell.date)}
                        >
                          <EventPill item={ev} today={today} />
                        </button>
                      ))}
                      {dayEvents.length > 3 && (
                        <button
                          type="button"
                          className="link-btn small"
                          onClick={() => setDayModalDate(cell.date)}
                        >
                          +{dayEvents.length - 3} mais
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <ol className="agenda" aria-label="Agenda do mês no celular">
            {dayGroups.map((group) => (
              <li
                key={`mob-${group.date}`}
                className={`agenda__day ${group.date === today ? "is-today" : ""}`}
              >
                <h3>{dayLongLabel(group.date, today)}</h3>
                <ul className="agenda__list">{group.items.map(renderTimelineRow)}</ul>
              </li>
            ))}
          </ol>
        </>
      )}

      {!timelineQuery.isPending && view !== "month" && dayGroups.length > 0 && (
        <ol className="agenda agenda--always" aria-label="Linha do tempo 360°">
          {dayGroups.map((group) => (
            <li
              key={group.date}
              className={`agenda__day ${group.date === today ? "is-today" : ""}`}
            >
              <h3>{dayLongLabel(group.date, today)}</h3>
              <ul className="agenda__list">{group.items.map(renderTimelineRow)}</ul>
            </li>
          ))}
        </ol>
      )}

      <Sheet
        open={Boolean(dayModalDate)}
        title={dayModalDate ? dayLongLabel(dayModalDate, today) : ""}
        onClose={() => setDayModalDate(null)}
      >
        {dayModalDate && (
          <div className="stack">
            {dayModalEvents.length === 0 ? (
              <p className="muted">Nada programado para este dia.</p>
            ) : (
              <ul className="agenda__list">{dayModalEvents.map(renderTimelineRow)}</ul>
            )}
            <Button
              type="button"
              onClick={() => {
                const picked = dayModalDate;
                setDayModalDate(null);
                openNewEvent(picked);
              }}
            >
              <CalendarPlus size={16} /> Agendar compromisso neste dia
            </Button>
          </div>
        )}
      </Sheet>

      <AgendaEventSheet
        open={eventOpen}
        defaultDate={eventDefaultDate}
        today={today}
        bridges={bridges}
        onClose={() => setEventOpen(false)}
        onSaved={() => {
          invalidateAgenda();
          setFeedback("Compromisso salvo na Agenda.");
        }}
      />

      <WhatsappConfirmSheet
        item={confirmItem}
        initialText={confirmText}
        chatName={confirmChatName}
        hasChat={confirmHasChat}
        onClose={() => setConfirmItem(null)}
        onSent={() => setFeedback("Confirmação enviada para a fila da Mensageria (WhatsApp).")}
      />
    </div>
  );
}
