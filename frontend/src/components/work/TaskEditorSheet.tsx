import { useEffect, useState, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { CheckSquare, Trash2 } from "lucide-react";

import { errorMessage } from "../../api/client";
import {
  projectsApi,
  type ChecklistItem,
  type ProjectTask,
  type TaskPriority,
  type TaskStatus,
} from "../../api/work";
import { TASK_PRIORITY_LABELS, TASK_STATUS_LABELS } from "../../lib/work";
import { DateField } from "../DateField";
import { Alert, Button, Sheet } from "../ui";

const STATUS_COLUMNS: TaskStatus[] = ["todo", "doing", "done"];

/** Folha modal para criar ou editar tarefa do Kanban com checklist e prazo integrado à Agenda. */
export function TaskEditorSheet({
  open,
  projectId,
  editingTask,
  onClose,
  onSaved,
}: {
  open: boolean;
  projectId: string | null;
  editingTask: ProjectTask | null;
  onClose: () => void;
  onSaved: (message: string) => void;
}) {
  const [title, setTitle] = useState("");
  const [desc, setDesc] = useState("");
  const [status, setStatus] = useState<TaskStatus>("todo");
  const [priority, setPriority] = useState<TaskPriority>("medium");
  const [due, setDue] = useState("");
  const [checklist, setChecklist] = useState<ChecklistItem[]>([]);
  const [newCheckItem, setNewCheckItem] = useState("");
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    if (editingTask) {
      setTitle(editingTask.title);
      setDesc(editingTask.description ?? "");
      setStatus(editingTask.status);
      setPriority(editingTask.priority);
      setDue(editingTask.due_date ?? "");
      setChecklist(editingTask.checklist ?? []);
    } else {
      setTitle("");
      setDesc("");
      setStatus("todo");
      setPriority("medium");
      setDue("");
      setChecklist([]);
    }
    setNewCheckItem("");
    setErr(null);
  }, [open, editingTask]);

  const saveTask = useMutation({
    mutationFn: () => {
      if (editingTask) {
        return projectsApi.updateTask(editingTask.id, {
          title: title.trim(),
          description: desc.trim() || null,
          status,
          priority,
          due_date: due || null,
          checklist,
        });
      }
      return projectsApi.createTask(projectId!, {
        title: title.trim(),
        description: desc.trim() || undefined,
        status,
        priority,
        due_date: due || null,
        checklist: checklist.map((c) => ({ text: c.text, done: c.done })),
      });
    },
    onSuccess: () => {
      onClose();
      onSaved(editingTask ? "Tarefa atualizada." : "Tarefa adicionada ao Kanban.");
    },
    onError: (e) => setErr(errorMessage(e)),
  });

  function addChecklistRow() {
    const clean = newCheckItem.trim();
    if (!clean) return;
    setChecklist((prev) => [
      ...prev,
      { id: `${Date.now()}-${Math.random().toString(36).slice(2, 6)}`, text: clean, done: false },
    ]);
    setNewCheckItem("");
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!title.trim()) {
      setErr("Informe o título da tarefa.");
      return;
    }
    saveTask.mutate();
  }

  return (
    <Sheet
      open={open}
      title={editingTask ? "Editar tarefa" : "Nova tarefa"}
      onClose={onClose}
    >
      <form className="inline-form stack" onSubmit={submit}>
        {err && <Alert tone="error">{err}</Alert>}

        <label className="field">
          <span className="field-label">Título da tarefa</span>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            placeholder="Ex.: Configurar domínio e certificado"
          />
        </label>

        <fieldset className="radios">
          <legend className="field-label">Prioridade</legend>
          <div className="chips">
            {(Object.keys(TASK_PRIORITY_LABELS) as TaskPriority[]).map((pr) => (
              <button
                key={pr}
                type="button"
                className="chip-btn"
                aria-pressed={priority === pr}
                onClick={() => setPriority(pr)}
              >
                {TASK_PRIORITY_LABELS[pr]}
              </button>
            ))}
          </div>
        </fieldset>

        <div className="grid-2">
          <label className="field">
            <span className="field-label">Coluna</span>
            <select value={status} onChange={(e) => setStatus(e.target.value as TaskStatus)}>
              {STATUS_COLUMNS.map((st) => (
                <option key={st} value={st}>
                  {TASK_STATUS_LABELS[st]}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field-label">Prazo (integra à Agenda)</span>
            <DateField value={due} onChange={setDue} label="Prazo da tarefa" />
          </label>
        </div>

        <div className="stack stack--tight">
          <span className="field-label">
            Checklist ({checklist.filter((c) => c.done).length}/{checklist.length})
          </span>
          <div className="row">
            <input
              value={newCheckItem}
              onChange={(e) => setNewCheckItem(e.target.value)}
              placeholder="Ex.: Validar apontamento DNS"
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  addChecklistRow();
                }
              }}
            />
            <button type="button" className="btn btn--secondary btn--sm" onClick={addChecklistRow}>
              <CheckSquare size={14} /> Incluir
            </button>
          </div>
          {checklist.map((item) => (
            <div key={item.id} className="split">
              <label className="check-row">
                <input
                  type="checkbox"
                  checked={item.done}
                  onChange={() =>
                    setChecklist((prev) =>
                      prev.map((row) => (row.id === item.id ? { ...row, done: !row.done } : row)),
                    )
                  }
                />
                <span>{item.text}</span>
              </label>
              <button
                type="button"
                className="icon-btn icon-btn--bordered"
                aria-label="Remover item do checklist"
                onClick={() => setChecklist((prev) => prev.filter((row) => row.id !== item.id))}
              >
                <Trash2 size={13} />
              </button>
            </div>
          ))}
        </div>

        <div className="field">
          <label htmlFor="task-desc" className="field-label">
            Notas da tarefa
          </label>
          <textarea
            id="task-desc"
            rows={2}
            value={desc}
            onChange={(e) => setDesc(e.target.value)}
          />
        </div>

        <div className="form-actions">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" loading={saveTask.isPending}>
            {editingTask ? "Salvar tarefa" : "Adicionar tarefa"}
          </Button>
        </div>
      </form>
    </Sheet>
  );
}
