import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { errorMessage } from "../../api/client";
import { messagingApi, type MessagingChat, type MessagingMessage } from "../../api/messaging";
import { todayISO } from "../../lib/format";
import { DateField } from "../DateField";
import { Sheet } from "../ui";

/** Folha modal para transformar conversa ou mensagem em Tarefa de Projeto ou Compromisso da Agenda. */
export function WorkActionSheet({
  chat,
  trigger,
  open,
  onClose,
}: {
  chat: MessagingChat;
  trigger: { seq: number; message?: MessagingMessage } | null;
  open: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [workMode, setWorkMode] = useState<"task" | "event">("task");
  const [workTitle, setWorkTitle] = useState("");
  const [workProjectId, setWorkProjectId] = useState("");
  const [workMsgId, setWorkMsgId] = useState<string | null>(null);
  const [workDate, setWorkDate] = useState(() => todayISO());
  const [workTime, setWorkTime] = useState("10:00");
  const [workLocation, setWorkLocation] = useState("");
  const [workNotice, setWorkNotice] = useState<string | null>(null);

  const workCtx = useQuery({
    queryKey: ["messaging", "work-context", chat.id],
    queryFn: () => messagingApi.workContext(chat.id),
    enabled: open,
  }).data;

  const workMutation = useMutation({
    mutationFn: async () => {
      if (workMode === "task") {
        const res = await messagingApi.createWorkTask(chat.id, {
          title: workTitle.trim(),
          project_id: workProjectId || null,
          message_id: workMsgId,
          due_date: workDate || null,
        });
        return `Tarefa criada no projeto "${res.project_name}".`;
      }
      const ev = await messagingApi.createAgendaEvent(chat.id, {
        title: workTitle.trim(),
        start_at: `${workDate}T${workTime || "10:00"}:00`,
        location: workLocation.trim() || null,
      });
      return `Compromisso "${ev.title}" agendado na Agenda 360°.`;
    },
    onSuccess: (msg) => {
      setWorkNotice(msg);
      void qc.invalidateQueries({ queryKey: ["projects"] });
      void qc.invalidateQueries({ queryKey: ["agenda"] });
      window.setTimeout(() => {
        onClose();
        setWorkNotice(null);
      }, 1100);
    },
  });

  useEffect(() => {
    if (!trigger) return;
    const cleaned = (trigger.message?.body ?? "").replace(/\s+/g, " ").trim().slice(0, 140);
    setWorkMode("task");
    setWorkTitle(cleaned || `Atendimento ${chat.name}`);
    setWorkProjectId("");
    setWorkMsgId(trigger.message?.id ?? null);
    setWorkDate(todayISO());
    setWorkTime("10:00");
    setWorkLocation("");
    setWorkNotice(null);
    workMutation.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trigger?.seq, chat.name]);

  return (
    <Sheet open={open} title="Transformar em Tarefa ou Agenda" onClose={onClose}>
      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault();
          if (!workTitle.trim() || workMutation.isPending || workMutation.isSuccess) return;
          workMutation.mutate();
        }}
      >
        <div className="wa-filters wa-filters--flush" role="group" aria-label="Destino">
          <button
            type="button"
            className="filter-chip"
            aria-pressed={workMode === "task"}
            disabled={workCtx?.projects_blocked}
            onClick={() => setWorkMode("task")}
          >
            Tarefa em Projeto
          </button>
          <button
            type="button"
            className="filter-chip"
            aria-pressed={workMode === "event"}
            disabled={workCtx?.agenda_blocked}
            onClick={() => setWorkMode("event")}
          >
            Compromisso na Agenda
          </button>
        </div>

        <div className="field">
          <label htmlFor="wa-work-title">Título</label>
          <input
            id="wa-work-title"
            type="text"
            className="input"
            required
            maxLength={160}
            value={workTitle}
            onChange={(e) => setWorkTitle(e.target.value)}
          />
        </div>

        {workMode === "task" ? (
          <div className="grid-2">
            <div className="field">
              <label htmlFor="wa-work-proj">Projeto</label>
              <select
                id="wa-work-proj"
                className="input"
                value={workProjectId}
                onChange={(e) => setWorkProjectId(e.target.value)}
              >
                <option value="">Criar/usar projeto Atendimento · {chat.name}</option>
                {(workCtx?.projects ?? []).map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="wa-work-due">Prazo (opcional)</label>
              <DateField id="wa-work-due" value={workDate} onChange={setWorkDate} />
            </div>
          </div>
        ) : (
          <div className="stack">
            <div className="grid-2">
              <div className="field">
                <label htmlFor="wa-agenda-date">Data</label>
                <DateField id="wa-agenda-date" value={workDate} onChange={setWorkDate} required />
              </div>
              <div className="field">
                <label htmlFor="wa-agenda-time">Horário</label>
                <input
                  id="wa-agenda-time"
                  type="time"
                  className="input"
                  value={workTime}
                  onChange={(e) => setWorkTime(e.target.value)}
                />
              </div>
            </div>
            <div className="field">
              <label htmlFor="wa-agenda-loc">Local ou link (opcional)</label>
              <input
                id="wa-agenda-loc"
                type="text"
                className="input"
                value={workLocation}
                onChange={(e) => setWorkLocation(e.target.value)}
              />
            </div>
          </div>
        )}

        {workMutation.isError && (
          <p className="alert alert--error" role="alert">
            {errorMessage(workMutation.error)}
          </p>
        )}
        {workNotice && (
          <p className="alert alert--success" role="status">
            {workNotice}
          </p>
        )}

        <div className="row row--right">
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            Cancelar
          </button>
          <button
            type="submit"
            className="btn btn--primary"
            disabled={!workTitle.trim() || workMutation.isPending || workMutation.isSuccess}
          >
            {workMutation.isPending
              ? "Salvando…"
              : workMode === "task"
                ? "Criar tarefa"
                : "Agendar compromisso"}
          </button>
        </div>
      </form>
    </Sheet>
  );
}
