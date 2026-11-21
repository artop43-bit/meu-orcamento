import { useEffect, useState, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";

import { errorMessage } from "../../api/client";
import { projectsApi, type ProjectTask, type WorkProject } from "../../api/work";
import { money, todayISO } from "../../lib/format";
import { DateField } from "../DateField";
import { Alert, Button, Sheet } from "../ui";

/** Folha modal para apontar horas trabalhadas e calcular o ganho real por hora do projeto. */
export function TimeEntrySheet({
  open,
  project,
  tasks,
  onClose,
  onSaved,
}: {
  open: boolean;
  project: WorkProject | undefined;
  tasks: ProjectTask[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [taskId, setTaskId] = useState("");
  const [hours, setHours] = useState("1");
  const [entryDate, setEntryDate] = useState(() => todayISO());
  const [notes, setNotes] = useState("");
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setTaskId("");
    setHours("1");
    setEntryDate(todayISO());
    setNotes("");
    setErr(null);
  }, [open]);

  const addTimeEntry = useMutation({
    mutationFn: () =>
      projectsApi.addTimeEntry(project!.id, {
        task_id: taskId || null,
        hours: Number(hours.replace(",", ".")),
        entry_date: entryDate || todayISO(),
        notes: notes.trim() || undefined,
      }),
    onSuccess: () => {
      onClose();
      onSaved();
    },
    onError: (e) => setErr(errorMessage(e)),
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    const h = Number(hours.replace(",", "."));
    if (!Number.isFinite(h) || h <= 0) {
      setErr("Informe uma quantidade de horas maior que zero.");
      return;
    }
    addTimeEntry.mutate();
  }

  const activeHoursNum = project ? Number(project.total_hours) : 0;
  const activeNetMarginNum = project ? Number(project.net_margin) : 0;
  const addedHoursNum = Number(hours.replace(",", ".")) || 0;
  const previewHoursTotal = activeHoursNum + addedHoursNum;
  const previewHourlyAfter =
    project && previewHoursTotal > 0 ? activeNetMarginNum / previewHoursTotal : 0;

  return (
    <Sheet open={open} title="Apontar horas trabalhadas" onClose={onClose}>
      <form className="inline-form stack" onSubmit={submit}>
        {err && <Alert tone="error">{err}</Alert>}

        <div className="stack stack--tight">
          <span className="field-label">Atalho de duração</span>
          <div className="chips">
            {["0,5", "1", "2", "4", "8"].map((preset) => (
              <button
                key={preset}
                type="button"
                className="chip-btn"
                aria-pressed={hours === preset}
                onClick={() => setHours(preset)}
              >
                {preset}h
              </button>
            ))}
          </div>
        </div>

        <div className="grid-2">
          <label className="field">
            <span className="field-label">Horas</span>
            <input
              type="number"
              step="0.01"
              min="0.01"
              value={hours.replace(",", ".")}
              onChange={(e) => setHours(e.target.value)}
              required
            />
          </label>
          <label className="field">
            <span className="field-label">Data</span>
            <DateField value={entryDate} onChange={setEntryDate} required label="Data do apontamento" />
          </label>
        </div>

        <label className="field">
          <span className="field-label">Tarefa relacionada (opcional)</span>
          <select value={taskId} onChange={(e) => setTaskId(e.target.value)}>
            <option value="">Geral do projeto</option>
            {tasks.map((t) => (
              <option key={t.id} value={t.id}>
                {t.title}
              </option>
            ))}
          </select>
        </label>

        {project && addedHoursNum > 0 && (
          <div className="summary-box">
            <div className="split small">
              <span>Total acumulado após apontar</span>
              <strong>{previewHoursTotal.toFixed(1).replace(".", ",")} h</strong>
            </div>
            <div className="split">
              <span>Novo ganho real por hora</span>
              <strong className="tone--ok">{money(previewHourlyAfter)}/h</strong>
            </div>
          </div>
        )}

        <div className="field">
          <label htmlFor="time-notes" className="field-label">
            O que foi entregue
          </label>
          <textarea
            id="time-notes"
            rows={2}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </div>

        <div className="form-actions">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" loading={addTimeEntry.isPending}>
            Registrar horas
          </Button>
        </div>
      </form>
    </Sheet>
  );
}
