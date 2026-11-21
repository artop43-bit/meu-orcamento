import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  Clock,
  FolderKanban,
  Pencil,
  Plus,
  Search,
  Trash2,
  TrendingUp,
} from "lucide-react";

import { errorMessage } from "../../api/client";
import {
  projectsApi,
  useProjectDetail,
  useProjects,
  useProjectsBridges,
  type ProjectStatus,
  type ProjectTask,
  type TaskPriority,
  type TaskStatus,
  type WorkProject,
} from "../../api/work";
import { Badge, Bar } from "../../components/budget";
import { EmptyGuide } from "../../components/help";
import { Alert, Button, LoadingRegion, PageHeader, Skeleton } from "../../components/ui";
import { useUndo } from "../../components/undo";
import { ProjectEditorSheet } from "../../components/work/ProjectEditorSheet";
import { TaskEditorSheet } from "../../components/work/TaskEditorSheet";
import { TimeEntrySheet } from "../../components/work/TimeEntrySheet";
import { formatDateHeading, money, plural } from "../../lib/format";
import { normalizeText } from "../../lib/text";
import {
  formatIsoDateBr,
  PROJECT_STATUS_LABELS,
  TASK_PRIORITY_LABELS,
  TASK_STATUS_LABELS,
} from "../../lib/work";

const STATUS_COLUMNS: TaskStatus[] = ["todo", "doing", "done"];

function priorityTone(p: TaskPriority): "warn" | "accent" | "neutral" {
  if (p === "urgent" || p === "high") return "warn";
  if (p === "medium") return "accent";
  return "neutral";
}

export default function ProjectsPage() {
  const qc = useQueryClient();
  const undo = useUndo();
  const [statusFilter, setStatusFilter] = useState<ProjectStatus | "">("");
  const [search, setSearch] = useState("");

  // Busca todos para exibir contagens corretas nas pílulas de status.
  const projectsQuery = useProjects("");
  const allProjects = (projectsQuery.data ?? []).filter((p) => !undo.isHidden(p.id));

  const needle = normalizeText(search);
  const visibleProjects = allProjects.filter((p) => {
    if (statusFilter && p.status !== statusFilter) return false;
    if (!needle) return true;
    return normalizeText(`${p.name} ${p.contact_name ?? ""}`).includes(needle);
  });

  const [selectedId, setSelectedId] = useState<string | null | undefined>();
  const activeId = selectedId === null
    ? null
    : (visibleProjects.find((project) => project.id === selectedId) ?? visibleProjects[0])?.id ?? null;
  const detail = useProjectDetail(activeId).data;

  const [projOpen, setProjOpen] = useState(false);
  const [editingProject, setEditingProject] = useState<WorkProject | null>(null);
  const [taskOpen, setTaskOpen] = useState(false);
  const [editingTask, setEditingTask] = useState<ProjectTask | null>(null);
  const [timeOpen, setTimeOpen] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  const bridges = useProjectsBridges(projOpen).data;

  function invalidateAll() {
    void qc.invalidateQueries({ queryKey: ["projects"] });
    void qc.invalidateQueries({ queryKey: ["agenda"] });
  }

  function openProjectEditor(project: WorkProject | null = null) {
    setEditingProject(project);
    setProjOpen(true);
  }

  function openNewTask() {
    setEditingTask(null);
    setTaskOpen(true);
  }

  function openEditTask(task: ProjectTask) {
    setEditingTask(task);
    setTaskOpen(true);
  }

  const updateProjectStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: ProjectStatus }) =>
      projectsApi.update(id, { status }),
    onSuccess: () => invalidateAll(),
  });

  function deleteProjectWithUndo(projId: string, projName: string) {
    undo.remove({
      ids: [projId],
      message: `Projeto "${projName}" excluído`,
      commit: async () => {
        await projectsApi.delete(projId);
        setSelectedId((prev) => (prev === projId ? undefined : prev));
        invalidateAll();
      },
    });
  }

  const moveTaskStatus = useMutation({
    mutationFn: ({ taskId, status }: { taskId: string; status: TaskStatus }) =>
      projectsApi.updateTask(taskId, { status }),
    onSuccess: () => invalidateAll(),
  });

  const toggleChecklistInline = useMutation({
    mutationFn: ({ task, itemId }: { task: ProjectTask; itemId: string }) => {
      const updated = (task.checklist ?? []).map((it) =>
        it.id === itemId ? { ...it, done: !it.done } : it,
      );
      return projectsApi.updateTask(task.id, { checklist: updated });
    },
    onSuccess: () => invalidateAll(),
  });

  function deleteTaskWithUndo(task: ProjectTask) {
    undo.remove({
      ids: [task.id],
      message: `Tarefa "${task.title}" excluída`,
      commit: async () => {
        await projectsApi.deleteTask(task.id);
        invalidateAll();
      },
    });
  }

  function deleteTimeEntryWithUndo(entryId: string) {
    undo.remove({
      ids: [entryId],
      message: "Apontamento de horas excluído",
      commit: async () => {
        await projectsApi.deleteTimeEntry(entryId);
        invalidateAll();
      },
    });
  }

  const totalHoursAll = allProjects.reduce((acc, p) => acc + Number(p.total_hours), 0);
  const totalMarginAll = allProjects.reduce((acc, p) => acc + Number(p.net_margin), 0);
  const activeCount = allProjects.filter((p) => p.status === "active" || p.status === "review").length;
  const pendingTasksAll = allProjects.reduce((acc, p) => acc + p.tasks_todo + p.tasks_doing, 0);

  const activeProj = detail?.project;
  const activeBudgetNum = activeProj ? Number(activeProj.budget_value) : 0;
  const activeExpensesNum = activeProj ? Number(activeProj.expenses_total) : 0;
  const activeNetMarginNum = activeProj ? Number(activeProj.net_margin) : 0;
  const activeHoursNum = activeProj ? Number(activeProj.total_hours) : 0;
  const activeHourlyRateNum = activeProj ? Number(activeProj.hourly_rate) : 0;
  const spendPct = activeBudgetNum > 0 ? Math.round((activeExpensesNum / activeBudgetNum) * 100) : 0;

  return (
    <div className="stack">
      <PageHeader
        title="Projetos e entregas"
        subtitle="Acompanhe entregas em Kanban com checklists, horas trabalhadas e margem real ligada ao Meu Orçamento."
        actions={
          <Button type="button" onClick={() => openProjectEditor()}>
            <Plus size={16} /> Novo projeto
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

      {projectsQuery.isPending && (
        <LoadingRegion label="Carregando projetos">
          <Skeleton height={160} />
        </LoadingRegion>
      )}
      {projectsQuery.isError && <Alert tone="error">{errorMessage(projectsQuery.error)}</Alert>}

      {!projectsQuery.isPending && (
        <div className="greeting">
          <span className="greeting__date">{formatDateHeading()}</span>
          <p className="greeting__hello">
            {allProjects.length === 0
              ? "Nenhum projeto ativo por aqui ainda."
              : `Você tem ${activeCount} ${plural(activeCount, "projeto", "projetos")} em execução e ${pendingTasksAll} ${plural(pendingTasksAll, "tarefa pendente", "tarefas pendentes")}.`}
          </p>
          <p className="greeting__text">
            {totalHoursAll > 0
              ? `${totalHoursAll.toFixed(1).replace(".", ",")} h registradas no total · margem acumulada de ${money(totalMarginAll)}.`
              : "Vincule etiquetas do Meu Orçamento para calcular seu lucro líquido e ganho real por hora."}
          </p>
        </div>
      )}

      {allProjects.length === 0 && !projectsQuery.isPending ? (
        <section className="card">
          <EmptyGuide
            icon={<FolderKanban size={22} />}
            title="Organize entregas sem complicação"
            text="Crie um projeto do zero ou gere direto de um negócio do CRM, proposta aprovada ou conversa no WhatsApp. Controle etapas em Kanban e veja quanto cada hora rendeu descontando gastos do Orçamento."
            example={<>Ex.: “Implantação loja virtual” orçado em R$ 3.000 com etiqueta financeira conectada.</>}
            action={
              <Button type="button" onClick={() => openProjectEditor()}>
                <Plus size={16} /> Novo projeto
              </Button>
            }
          />
        </section>
      ) : (
        allProjects.length > 0 && (
          <>
            <div className="list-tools list-tools--pills person-tools" role="search" aria-label="Filtrar projetos">
              <label className="list-tools__search">
                <Search size={16} aria-hidden />
                <span className="sr-only">Buscar projeto ou cliente</span>
                <input
                  type="search"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Buscar projeto ou cliente..."
                />
              </label>
              <span className="pill-group" role="group" aria-label="Status do projeto">
                <button
                  type="button"
                  className="chip-btn"
                  aria-pressed={statusFilter === ""}
                  onClick={() => setStatusFilter("")}
                >
                  Todos ({allProjects.length})
                </button>
                {(Object.keys(PROJECT_STATUS_LABELS) as ProjectStatus[]).map((st) => (
                  <button
                    key={st}
                    type="button"
                    className="chip-btn"
                    aria-pressed={statusFilter === st}
                    onClick={() => setStatusFilter(st)}
                  >
                    {PROJECT_STATUS_LABELS[st]} ({allProjects.filter((p) => p.status === st).length})
                  </button>
                ))}
              </span>
            </div>

            {visibleProjects.length === 0 ? (
              <p className="muted">Nenhum projeto encontrado para este filtro.</p>
            ) : (
              <div className="person-rows" role="group" aria-label="Selecionar projeto">
                {visibleProjects.map((project) => {
                  const isOpen = activeId === project.id;
                  return (
                    <article key={project.id} className={`card person-row person-row--long person-row--project${isOpen ? " is-open" : ""}`} data-project-row={project.id}>
                      <button className="person-row__head" type="button" aria-expanded={isOpen}
                        onClick={() => setSelectedId(isOpen ? null : project.id)}>
                        <span className="person-row__avatar" aria-hidden><FolderKanban size={18} /></span>
                        <span className="person-row__who">
                          <strong title={project.name}>{project.name}</strong>
                          <span className="muted small">{PROJECT_STATUS_LABELS[project.status]}</span>
                        </span>
                        <span className={`person-row__balance ${Number(project.net_margin) < 0 ? "tone--error" : "tone--ok"}`}>
                          {money(project.net_margin)}
                        </span>
                        <span className="person-row__chev" aria-hidden><ChevronDown size={18} /></span>
                      </button>
                      {isOpen && <div className="person-row__body">
                        <div className="person-row__actions">
                          <button type="button" className="btn btn--secondary btn--sm"
                            onClick={() => openProjectEditor(project)}>
                            <Pencil size={14} aria-hidden /> Editar projeto
                          </button>
                          <button type="button" className="btn btn--secondary btn--sm"
                            aria-label={`Excluir projeto ${project.name}`}
                            onClick={() => deleteProjectWithUndo(project.id, project.name)}>
                            <Trash2 size={14} aria-hidden /> Excluir projeto
                          </button>
                        </div>
                      </div>}
                    </article>
                  );
                })}
              </div>
            )}

            {detail && activeProj && (
              <>
                <section className="card month-summary" aria-label={`Resumo de ${activeProj.name}`}>
                  <div className="month-summary__main">
                    <span className="month-summary__label">
                      <TrendingUp size={15} aria-hidden /> Margem líquida real · {activeProj.name}
                    </span>
                    <strong
                      className={`month-summary__value ${
                        activeNetMarginNum < 0 ? "tone--error" : "tone--ok"
                      }`}
                    >
                      {money(activeProj.net_margin)}
                    </strong>
                    <span className="muted small">
                      {activeProj.contact_name ? `${activeProj.contact_name} · ` : ""}
                      Orçado {money(activeProj.budget_value)}
                      {activeProj.due_date ? ` · Entrega ${formatIsoDateBr(activeProj.due_date)}` : ""}
                    </span>
                    {activeProj.description && <p className="muted small">{activeProj.description}</p>}
                  </div>
                  <div className="month-summary__side">
                    <dl className="month-summary__grid">
                      <div>
                        <dt>Despesas (Orçamento)</dt>
                        <dd className="month-summary__num">{money(activeProj.expenses_total)}</dd>
                        <dd className="month-summary__foot">
                          {activeProj.budget_project_id ? "Etiqueta conectada" : "Sem etiqueta financeira"}
                        </dd>
                      </div>
                      <div>
                        <dt>
                          <Clock size={14} aria-hidden /> Horas registradas
                        </dt>
                        <dd className="month-summary__num">
                          {activeHoursNum.toFixed(1).replace(".", ",")} h
                        </dd>
                        <dd className="month-summary__foot">
                          {activeProj.tasks_done} de {activeProj.tasks_total} {plural(activeProj.tasks_total, "tarefa", "tarefas")}
                        </dd>
                      </div>
                      <div>
                        <dt>Ganho real por hora</dt>
                        <dd className="month-summary__num tone--ok">
                          {money(activeProj.effective_hourly_rate)}/h
                        </dd>
                        <dd className="month-summary__foot">
                          {activeHourlyRateNum > 0
                            ? `Meta: ${money(activeProj.hourly_rate)}/h`
                            : "Baseado na margem"}
                        </dd>
                      </div>
                    </dl>
                    {activeBudgetNum > 0 && (
                      <div
                        className={`month-summary__bar ${
                          spendPct > 100 ? "is-over" : spendPct > 80 ? "is-high" : ""
                        }`}
                        role="img"
                        aria-label={`Despesas representam ${spendPct}% do orçado`}
                      >
                        <span style={{ width: `${Math.min(100, spendPct)}%` }} />
                      </div>
                    )}
                    <div className="split">
                      <div className="chips" role="group" aria-label="Status deste projeto">
                        {(Object.keys(PROJECT_STATUS_LABELS) as ProjectStatus[]).map((st) => (
                          <button
                            key={st}
                            type="button"
                            className="chip-btn"
                            aria-pressed={activeProj.status === st}
                            onClick={() =>
                              updateProjectStatus.mutate({ id: activeProj.id, status: st })
                            }
                          >
                            {PROJECT_STATUS_LABELS[st]}
                          </button>
                        ))}
                      </div>
                      <div className="row">
                        <button type="button" className="btn btn--primary btn--sm" onClick={openNewTask}>
                          <Plus size={14} /> Nova tarefa
                        </button>
                        <button
                          type="button"
                          className="btn btn--secondary btn--sm"
                          onClick={() => setTimeOpen(true)}
                        >
                          <Clock size={14} /> Apontar horas
                        </button>
                      </div>
                    </div>
                  </div>
                </section>

                <section className="crm-kanban" aria-label="Quadro de tarefas do projeto">
                  {STATUS_COLUMNS.map((colStatus) => {
                    const colTasks = detail.tasks.filter(
                      (t) => t.status === colStatus && !undo.isHidden(t.id),
                    );
                    return (
                      <div key={colStatus} className="crm-kanban__col">
                        <div className="crm-kanban__head">
                          <div className="split">
                            <strong>{TASK_STATUS_LABELS[colStatus]}</strong>
                            <Badge tone="neutral">{colTasks.length}</Badge>
                          </div>
                        </div>

                        <div className="crm-kanban__cards">
                          {colTasks.length === 0 ? (
                            <p className="muted small crm-kanban__empty">
                              Nenhuma tarefa nesta etapa.
                            </p>
                          ) : (
                            colTasks.map((task) => {
                              const totalChecks = task.checklist?.length ?? 0;
                              const doneChecks = (task.checklist ?? []).filter((c) => c.done).length;
                              const checkPct =
                                totalChecks > 0 ? Math.round((doneChecks / totalChecks) * 100) : 0;
                              return (
                                <article
                                  key={task.id}
                                  className="crm-deal-card"
                                  data-task-card={task.id}
                                >
                                  <button
                                    type="button"
                                    className="crm-deal-card__main"
                                    onClick={() => openEditTask(task)}
                                  >
                                    <span className="split">
                                      <strong className="crm-deal-card__title">{task.title}</strong>
                                      <Badge tone={priorityTone(task.priority)}>
                                        {TASK_PRIORITY_LABELS[task.priority]}
                                      </Badge>
                                    </span>
                                    {task.due_date && (
                                      <span className="muted small">
                                        Prazo {formatIsoDateBr(task.due_date)}
                                      </span>
                                    )}
                                  </button>

                                  {totalChecks > 0 && (
                                    <div className="stack stack--tight">
                                      <div className="split small muted">
                                        <span>Checklist</span>
                                        <span>
                                          {doneChecks}/{totalChecks}
                                        </span>
                                      </div>
                                      <Bar pct={checkPct} />
                                      <ul className="kanban-check-list">
                                        {task.checklist.slice(0, 4).map((item) => (
                                          <li key={item.id}>
                                            <label>
                                              <input
                                                type="checkbox"
                                                checked={item.done}
                                                onChange={() =>
                                                  toggleChecklistInline.mutate({
                                                    task,
                                                    itemId: item.id,
                                                  })
                                                }
                                              />
                                              <span className={item.done ? "muted" : ""}>
                                                {item.text}
                                              </span>
                                            </label>
                                          </li>
                                        ))}
                                      </ul>
                                    </div>
                                  )}

                                  <div className="split row--tight">
                                    <div className="kanban-moves" role="group" aria-label="Mover etapa">
                                      {STATUS_COLUMNS.filter((st) => st !== task.status).map((st) => (
                                        <button
                                          key={st}
                                          type="button"
                                          className="chip-btn"
                                          onClick={() =>
                                            moveTaskStatus.mutate({ taskId: task.id, status: st })
                                          }
                                        >
                                          {st === "done" ? (
                                            <CheckCircle2 size={12} />
                                          ) : (
                                            <ArrowRight size={12} />
                                          )}{" "}
                                          {TASK_STATUS_LABELS[st]}
                                        </button>
                                      ))}
                                    </div>
                                    <div className="row">
                                      <button
                                        type="button"
                                        className="icon-btn icon-btn--bordered"
                                        aria-label={`Editar ${task.title}`}
                                        onClick={() => openEditTask(task)}
                                      >
                                        <Pencil size={13} />
                                      </button>
                                      <button
                                        type="button"
                                        className="icon-btn icon-btn--bordered"
                                        aria-label={`Excluir tarefa ${task.title}`}
                                        onClick={() => deleteTaskWithUndo(task)}
                                      >
                                        <Trash2 size={13} />
                                      </button>
                                    </div>
                                  </div>
                                </article>
                              );
                            })
                          )}
                        </div>
                      </div>
                    );
                  })}
                </section>

                <details className="card details" open>
                  <summary>
                    Histórico de horas trabalhadas ({detail.time_entries.length})
                  </summary>
                  {detail.time_entries.length === 0 ? (
                    <EmptyGuide
                      icon={<Clock size={20} />}
                      title="Nenhuma hora apontada ainda"
                      text="Registre os blocos trabalhados para descobrir quanto este projeto realmente paga por hora."
                      action={
                        <button
                          type="button"
                          className="btn btn--secondary btn--sm"
                          onClick={() => setTimeOpen(true)}
                        >
                          <Clock size={14} /> Apontar horas
                        </button>
                      }
                    />
                  ) : (
                    <ul className="items">
                      {detail.time_entries
                        .filter((entry) => !undo.isHidden(entry.id))
                        .map((entry) => (
                        <li key={entry.id} className="item">
                          <span className="item__main">
                            <strong className="item__title">
                              {entry.task_title || "Trabalho geral no projeto"}
                            </strong>
                            <span className="item__meta">
                              {formatIsoDateBr(entry.entry_date)}
                              {entry.notes ? ` · ${entry.notes}` : ""}
                            </span>
                          </span>
                          <span className="row">
                            <Badge tone="accent">{Number(entry.hours).toFixed(1).replace(".", ",")} h</Badge>
                            <button
                              type="button"
                              className="icon-btn icon-btn--bordered"
                              aria-label="Excluir apontamento de horas"
                              onClick={() => deleteTimeEntryWithUndo(entry.id)}
                            >
                              <Trash2 size={13} />
                            </button>
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </details>
              </>
            )}
          </>
        )
      )}

      <ProjectEditorSheet
        open={projOpen}
        bridges={bridges}
        editing={editingProject}
        onClose={() => setProjOpen(false)}
        onSaved={(saved) => {
          setSelectedId(saved.id);
          invalidateAll();
          setFeedback(`Projeto "${saved.name}" ${editingProject ? "atualizado" : "criado"}.`);
        }}
      />

      <TaskEditorSheet
        open={taskOpen}
        projectId={activeId}
        editingTask={editingTask}
        onClose={() => setTaskOpen(false)}
        onSaved={(message) => {
          invalidateAll();
          setFeedback(message);
        }}
      />

      <TimeEntrySheet
        open={timeOpen}
        project={activeProj}
        tasks={detail?.tasks ?? []}
        onClose={() => setTimeOpen(false)}
        onSaved={() => {
          invalidateAll();
          setFeedback("Horas registradas no projeto.");
        }}
      />
    </div>
  );
}
