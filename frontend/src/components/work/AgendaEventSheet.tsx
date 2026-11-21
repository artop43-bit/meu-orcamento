import { useEffect, useState, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";

import { errorMessage } from "../../api/client";
import { agendaApi, type AgendaBridges, type AgendaEventKind } from "../../api/work";
import { announce } from "../../lib/announce";
import { AGENDA_KIND_LABELS } from "../../lib/work";
import { DateField } from "../DateField";
import { Tip } from "../help";
import { Alert, Button, Sheet } from "../ui";

/** Folha modal para criar um compromisso próprio na Agenda 360° com vínculos opcionais. */
export function AgendaEventSheet({
  open,
  defaultDate,
  today,
  bridges,
  onClose,
  onSaved,
}: {
  open: boolean;
  defaultDate: string;
  today: string;
  bridges: AgendaBridges | undefined;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState<AgendaEventKind>("meeting");
  const [datePart, setDatePart] = useState(defaultDate);
  const [timePart, setTimePart] = useState("09:00");
  const [allDay, setAllDay] = useState(false);
  const [location, setLocation] = useState("");
  const [projectId, setProjectId] = useState("");
  const [chatId, setChatId] = useState("");
  const [notes, setNotes] = useState("");
  const [formErr, setFormErr] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setTitle("");
    setKind("meeting");
    setDatePart(defaultDate);
    setTimePart("09:00");
    setAllDay(false);
    setLocation("");
    setProjectId("");
    setChatId("");
    setNotes("");
    setFormErr(null);
  }, [open, defaultDate]);

  const createEvent = useMutation({
    mutationFn: () => {
      const targetDate = datePart || today;
      const startIso = allDay ? `${targetDate}T08:00:00` : `${targetDate}T${timePart || "09:00"}:00`;
      return agendaApi.createEvent({
        title: title.trim(),
        kind,
        start_at: startIso,
        all_day: allDay,
        location: location.trim() || undefined,
        project_id: projectId || null,
        messaging_chat_id: chatId || null,
        notes: notes.trim() || undefined,
      });
    },
    onSuccess: () => {
      onClose();
      onSaved();
      announce("Compromisso salvo");
    },
    onError: (e) => setFormErr(errorMessage(e)),
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!title.trim()) {
      setFormErr("Informe o título do compromisso.");
      return;
    }
    createEvent.mutate();
  }

  return (
    <Sheet open={open} title="Novo compromisso" onClose={onClose}>
      <form className="inline-form stack" onSubmit={submit}>
        {formErr && <Alert tone="error">{formErr}</Alert>}

        <label className="field">
          <span className="field-label">Título</span>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            placeholder="Ex.: Visita técnica ou reunião de entrega"
          />
        </label>

        <div className="field">
          <span className="field-label">Tipo do compromisso</span>
          <div className="chips" role="group" aria-label="Tipo do compromisso">
            {(Object.keys(AGENDA_KIND_LABELS) as AgendaEventKind[]).map((k) => (
              <button
                key={k}
                type="button"
                className="chip-btn"
                aria-pressed={kind === k}
                onClick={() => setKind(k)}
              >
                {AGENDA_KIND_LABELS[k]}
              </button>
            ))}
          </div>
        </div>

        <div className="grid-2">
          <label className="field">
            <span className="field-label">Data</span>
            <DateField value={datePart} onChange={setDatePart} required label="Data do compromisso" />
          </label>
          <label className="field">
            <span className="field-label">Horário</span>
            <input
              type="time"
              value={timePart}
              disabled={allDay}
              onChange={(e) => setTimePart(e.target.value)}
            />
          </label>
        </div>

        <label className="check-row">
          <input type="checkbox" checked={allDay} onChange={(e) => setAllDay(e.target.checked)} />
          <span>Compromisso o dia inteiro</span>
        </label>

        <label className="field">
          <span className="field-label">Local / Link da chamada</span>
          <input
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            placeholder="Endereço ou sala de vídeo"
          />
        </label>

        <div className="grid-2">
          <label className="field">
            <span className="field-label">
              Conversa WhatsApp{" "}
              <Tip>Ao vincular uma conversa, você pode enviar a confirmação do compromisso em 1 toque.</Tip>
            </span>
            <select value={chatId} onChange={(e) => setChatId(e.target.value)}>
              <option value="">Sem vínculo</option>
              {(bridges?.chats ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field-label">Projeto relacionado</span>
            <select value={projectId} onChange={(e) => setProjectId(e.target.value)}>
              <option value="">Nenhum</option>
              {(bridges?.projects ?? []).map((pr) => (
                <option key={pr.id} value={pr.id}>
                  {pr.name}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="field">
          <label htmlFor="agenda-notes" className="field-label">
            Observações
          </label>
          <textarea
            id="agenda-notes"
            rows={2}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </div>

        <div className="form-actions">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" loading={createEvent.isPending}>
            Salvar compromisso
          </Button>
        </div>
      </form>
    </Sheet>
  );
}
