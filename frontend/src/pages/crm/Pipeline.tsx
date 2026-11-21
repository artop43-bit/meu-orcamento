import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Circle, FolderKanban, MessageCircle, Plus, Trash2, Wallet } from "lucide-react";

import { errorMessage } from "../../api/client";
import {
  crmApi,
  crmKeys,
  useContacts,
  usePipeline,
  type CrmActivity,
  type CrmDeal,
} from "../../api/crm";
import { DateField } from "../../components/DateField";
import { Alert, Kpi, PageHeader, Sheet } from "../../components/ui";
import { announce } from "../../lib/announce";
import { dealBudgetState, dealDeleteConfirmText, formatDateBr } from "../../lib/crm";
import { money, parseMoney } from "../../lib/format";

export default function Pipeline() {
  const qc = useQueryClient();
  const boardQuery = usePipeline();
  const contactsQuery = useContacts();
  const board = boardQuery.data;
  const contacts = contactsQuery.data ?? [];

  // Janela: Novo negócio
  const [newOpen, setNewOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [value, setValue] = useState("");
  const [stageId, setStageId] = useState("");
  const [contactId, setContactId] = useState("");
  const [expectedDate, setExpectedDate] = useState("");
  const [notes, setNotes] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  // Janela: Detalhe do negócio
  const [activeDeal, setActiveDeal] = useState<CrmDeal | null>(null);
  const [actBody, setActBody] = useState("");
  const [actKind, setActKind] = useState<CrmActivity["kind"]>("note");
  const [syncMsg, setSyncMsg] = useState<string | null>(null);
  const [syncErr, setSyncErr] = useState<string | null>(null);

  const activitiesQuery = useQuery({
    queryKey: crmKeys.activities(activeDeal?.id ?? null, null),
    queryFn: () => crmApi.activities({ dealId: activeDeal!.id }),
    enabled: Boolean(activeDeal),
  });

  const createDeal = useMutation({
    mutationFn: crmApi.createDeal,
    onSuccess: () => {
      setNewOpen(false);
      setTitle("");
      setValue("");
      setExpectedDate("");
      setNotes("");
      setFormError(null);
      void qc.invalidateQueries({ queryKey: crmKeys.pipeline });
      void qc.invalidateQueries({ queryKey: ["crm", "dashboard"] });
      void qc.invalidateQueries({ queryKey: crmKeys.sources });
      announce("Negócio criado no funil.");
    },
    onError: (err) => setFormError(errorMessage(err)),
  });

  const updateDeal = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Record<string, unknown> }) =>
      crmApi.updateDeal(id, data),
    onSuccess: (updated) => {
      if (activeDeal?.id === updated.id) setActiveDeal(updated);
      void qc.invalidateQueries({ queryKey: crmKeys.pipeline });
      void qc.invalidateQueries({ queryKey: ["crm", "dashboard"] });
      void qc.invalidateQueries({ queryKey: crmKeys.sources });
    },
  });

  const deleteDeal = useMutation({
    mutationFn: crmApi.deleteDeal,
    onSuccess: () => {
      setActiveDeal(null);
      void qc.invalidateQueries({ queryKey: crmKeys.pipeline });
      void qc.invalidateQueries({ queryKey: ["crm", "dashboard"] });
      void qc.invalidateQueries({ queryKey: crmKeys.sources });
      announce("Negócio excluído.");
    },
  });

  const syncBudget = useMutation({
    mutationFn: crmApi.syncDealBudget,
    onSuccess: (res) => {
      setSyncErr(null);
      setSyncMsg(`Receita de ${money(res.amount)} lançada no Meu Orçamento.`);
      void qc.invalidateQueries({ queryKey: crmKeys.pipeline });
      void qc.invalidateQueries({ queryKey: ["budget"] });
      if (activeDeal) {
        setActiveDeal({ ...activeDeal, budget_income_id: res.budget_income_id });
        void qc.invalidateQueries({ queryKey: crmKeys.activities(activeDeal.id, null) });
      }
      announce("Receita lançada no Meu Orçamento.");
    },
    onError: (err) => {
      setSyncMsg(null);
      setSyncErr(errorMessage(err));
    },
  });

  const createProject = useMutation({
    mutationFn: crmApi.createDealProject,
    onSuccess: (res) => {
      setSyncErr(null);
      setSyncMsg(
        res.created
          ? `Projeto "${res.project.name}" criado em Projetos & Tarefas.`
          : `Projeto "${res.project.name}" já existe em Projetos & Tarefas.`,
      );
      if (activeDeal) void qc.invalidateQueries({ queryKey: crmKeys.activities(activeDeal.id, null) });
      void qc.invalidateQueries({ queryKey: ["projects"] });
    },
    onError: (err) => {
      setSyncMsg(null);
      setSyncErr(errorMessage(err));
    },
  });

  const addActivity = useMutation({
    mutationFn: crmApi.createActivity,
    onSuccess: () => {
      setActBody("");
      if (activeDeal) void qc.invalidateQueries({ queryKey: crmKeys.activities(activeDeal.id, null) });
    },
  });

  const toggleActivity = useMutation({
    mutationFn: ({ id, done }: { id: string; done: boolean }) => crmApi.toggleActivity(id, done),
    onSuccess: () => {
      if (activeDeal) void qc.invalidateQueries({ queryKey: crmKeys.activities(activeDeal.id, null) });
    },
  });

  function submitNew(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    const amount = parseMoney(value || "0");
    if (amount === null) {
      setFormError("Informe um valor válido, como 1.234,56.");
      return;
    }
    createDeal.mutate({
      title,
      value: amount,
      stage_id: stageId || board?.stages[0]?.id,
      contact_id: contactId || null,
      expected_close_date: expectedDate || null,
      notes: notes || undefined,
    });
  }

  function submitActivity(event: FormEvent) {
    event.preventDefault();
    if (!activeDeal || !actBody.trim()) return;
    addActivity.mutate({
      deal_id: activeDeal.id,
      kind: actKind,
      body: actBody.trim(),
    });
  }

  return (
    <div className="stack">
      <PageHeader
        title="Funil CRM"
        subtitle="Acompanhe oportunidades por etapa e lance vendas ganhas direto no Meu Orçamento."
        actions={
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => {
              setStageId(board?.stages[0]?.id ?? "");
              setFormError(null);
              setNewOpen(true);
            }}
          >
            <Plus size={16} aria-hidden />
            Novo negócio
          </button>
        }
      />

      {boardQuery.isError && <Alert tone="error">{errorMessage(boardQuery.error)}</Alert>}
      {updateDeal.isError && <Alert tone="error">{errorMessage(updateDeal.error)}</Alert>}
      {board && (
        <div className="kpis">
          <Kpi icon={<Wallet size={18} />} label="Em andamento" value={money(board.summary.open_value)} />
          <Kpi icon={<CheckCircle2 size={18} />} label="Ganhos" value={money(board.summary.won_value)} />
          <Kpi icon={<Circle size={18} />} label="Total de negócios" value={board.summary.total_deals} tone="neutral" />
        </div>
      )}

      {boardQuery.isPending ? (
        <div className="card">
          <p className="muted small">Carregando funil…</p>
        </div>
      ) : board ? (
        <div className="crm-kanban">
          {board.stages.map((stage) => (
            <section key={stage.id} className="crm-kanban__col" aria-label={`Etapa ${stage.name}`}>
              <header className="crm-kanban__head">
                <div className="row">
                  <strong>{stage.name}</strong>
                  <span
                    className={`badge ${
                      stage.is_won ? "badge--ok" : stage.is_lost ? "badge--error" : "badge--muted"
                    }`}
                  >
                    {stage.deals.length}
                  </span>
                </div>
                <span className="muted small">{money(stage.total_value)}</span>
              </header>

              <div className="crm-kanban__cards">
                {stage.deals.length === 0 ? (
                  <p className="muted small crm-kanban__empty">Sem negócios</p>
                ) : (
                  stage.deals.map((deal) => (
                    <article key={deal.id} className="crm-deal-card">
                      <button
                        type="button"
                        className="crm-deal-card__main"
                        onClick={() => {
                          setSyncMsg(null);
                          setSyncErr(null);
                          setActiveDeal(deal);
                        }}
                      >
                        <strong className="crm-deal-card__title">{deal.title}</strong>
                        <span className="crm-deal-card__value">{money(deal.value)}</span>
                        {deal.contact_name && <span className="muted small">{deal.contact_name}</span>}
                        {deal.expected_close_date && (
                          <span className="muted small">
                            Previsão: {formatDateBr(deal.expected_close_date)}
                          </span>
                        )}
                      </button>
                      <div className="crm-deal-card__foot">
                        <label className="sr-only" htmlFor={`stage-${deal.id}`}>
                          Mover etapa
                        </label>
                        <select
                          id={`stage-${deal.id}`}
                          className="crm-deal-card__stage"
                          value={deal.stage_id}
                          onChange={(e) =>
                            updateDeal.mutate({ id: deal.id, data: { stage_id: e.target.value } })
                          }
                        >
                          {board.stages.map((s) => (
                            <option key={s.id} value={s.id}>
                              {s.name}
                            </option>
                          ))}
                        </select>
                        {deal.budget_income_id && (
                          <span className="badge badge--ok" title="Receita lançada no Meu Orçamento">
                            Orçamento
                          </span>
                        )}
                      </div>
                    </article>
                  ))
                )}
              </div>
            </section>
          ))}
        </div>
      ) : null}

      {/* Janela: Novo negócio */}
      <Sheet open={newOpen} title="Novo negócio" onClose={() => setNewOpen(false)}>
        <form className="inline-form stack" onSubmit={submitNew}>
          {formError && (
            <Alert tone="error">
              {formError}
            </Alert>
          )}
          <label className="field">
            <span className="field-label">Título do negócio</span>
            <input
              type="text"
              required
              placeholder="Ex.: Consultoria mensal"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </label>
          <div className="grid-2">
            <label className="field">
              <span className="field-label">Valor (R$)</span>
              <input
                type="text"
                inputMode="decimal"
                placeholder="1500,00"
                value={value}
                onChange={(e) => setValue(e.target.value)}
              />
            </label>
            <label className="field">
              <span className="field-label">Previsão de fechamento</span>
              <DateField
                value={expectedDate}
                onChange={setExpectedDate}
                label="Previsão de fechamento"
              />
            </label>
          </div>
          <div className="grid-2">
            <label className="field">
              <span className="field-label">Etapa inicial</span>
              <select value={stageId} onChange={(e) => setStageId(e.target.value)}>
                {(board?.stages ?? []).map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span className="field-label">Contato vinculado</span>
              <select value={contactId} onChange={(e) => setContactId(e.target.value)}>
                <option value="">Sem contato</option>
                {contacts.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label className="field">
            <span className="field-label">Observações</span>
            <textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
          </label>
          <div className="form-actions">
            <button type="button" className="btn btn--secondary" onClick={() => setNewOpen(false)}>
              Cancelar
            </button>
            <button type="submit" className="btn btn--primary" disabled={createDeal.isPending}>
              {createDeal.isPending ? "Salvando…" : "Salvar negócio"}
            </button>
          </div>
        </form>
      </Sheet>

      {/* Janela: Detalhes do negócio, ponte com Meu Orçamento e atividades */}
      <Sheet
        open={Boolean(activeDeal)}
        title={activeDeal?.title ?? "Negócio"}
        onClose={() => setActiveDeal(null)}
      >
        {activeDeal && (
          <div className="stack">
            <div className="stack stack--tight">
              <div className="split">
                <strong>{money(activeDeal.value)}</strong>
                <span
                  className={`badge ${
                    activeDeal.status === "won"
                      ? "badge--ok"
                      : activeDeal.status === "lost"
                        ? "badge--error"
                        : "badge--accent"
                  }`}
                >
                  {activeDeal.status === "won"
                    ? "Ganho"
                    : activeDeal.status === "lost"
                      ? "Perdido"
                      : "Em andamento"}
                </span>
              </div>
              {activeDeal.contact_name && (
                <p className="muted small">
                  Contato: {activeDeal.contact_name}
                  {activeDeal.contact_phone ? ` · ${activeDeal.contact_phone}` : ""}
                </p>
              )}
              {activeDeal.contact_messaging_chat_id && (
                <span className="row small">
                  <MessageCircle size={14} aria-hidden />
                  <span>Conversa vinculada na Mensageria (acesse pelo Hub)</span>
                </span>
              )}
            </div>

            <div className="row">
              {dealBudgetState(activeDeal) === "sent" && (
                <span className="badge badge--ok">Receita lançada no Meu Orçamento</span>
              )}
              {dealBudgetState(activeDeal) === "can_send" && (
                <button
                  type="button"
                  className="btn btn--primary btn--sm"
                  disabled={syncBudget.isPending}
                  onClick={() => syncBudget.mutate(activeDeal.id)}
                >
                  <Wallet size={15} aria-hidden />
                  Enviar receita ao Meu Orçamento
                </button>
              )}
              <button
                type="button"
                className="btn btn--secondary btn--sm"
                disabled={createProject.isPending}
                onClick={() => createProject.mutate(activeDeal.id)}
              >
                <FolderKanban size={15} aria-hidden />
                Abrir projeto
              </button>
              <button
                type="button"
                className="btn btn--danger btn--sm"
                disabled={deleteDeal.isPending}
                onClick={() => {
                  if (window.confirm(dealDeleteConfirmText(activeDeal))) deleteDeal.mutate(activeDeal.id);
                }}
              >
                <Trash2 size={15} aria-hidden />
                Excluir
              </button>
            </div>

            {deleteDeal.isError && <Alert tone="error">{errorMessage(deleteDeal.error)}</Alert>}
            {addActivity.isError && <Alert tone="error">{errorMessage(addActivity.error)}</Alert>}
            {toggleActivity.isError && <Alert tone="error">{errorMessage(toggleActivity.error)}</Alert>}

            {syncMsg && (
              <Alert tone="success">
                {syncMsg}
              </Alert>
            )}
            {syncErr && (
              <Alert tone="error">
                {syncErr}
              </Alert>
            )}

            <div className="stack stack--tight">
              <h3>Atividades</h3>
              <form className="row crm-activity-form" onSubmit={submitActivity}>
                <select
                  aria-label="Tipo de atividade"
                  value={actKind}
                  onChange={(e) => setActKind(e.target.value as CrmActivity["kind"])}
                >
                  <option value="note">Nota</option>
                  <option value="task">Tarefa</option>
                  <option value="call">Ligação</option>
                  <option value="message">Mensagem</option>
                </select>
                <input
                  type="text"
                  placeholder="Registrar anotação ou tarefa"
                  aria-label="Texto da atividade"
                  value={actBody}
                  onChange={(e) => setActBody(e.target.value)}
                />
                <button type="submit" className="btn btn--primary btn--sm" disabled={!actBody.trim()}>
                  Salvar
                </button>
              </form>

              <ul className="items">
                {(activitiesQuery.data ?? []).map((act) => (
                  <li key={act.id} className="item">
                    <button
                      type="button"
                      className="icon-btn"
                      onClick={() => toggleActivity.mutate({ id: act.id, done: !act.done_at })}
                      aria-label={act.done_at ? "Desmarcar atividade" : "Concluir atividade"}
                    >
                      {act.done_at ? (
                        <CheckCircle2 size={16} aria-hidden />
                      ) : (
                        <Circle size={16} aria-hidden />
                      )}
                    </button>
                    <div className="item__main">
                      <span className={act.done_at ? "muted" : undefined}>{act.body}</span>
                      <span className="muted small">{act.kind}</span>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </Sheet>
    </div>
  );
}
