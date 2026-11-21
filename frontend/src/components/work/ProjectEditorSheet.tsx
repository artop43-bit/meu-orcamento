import { useEffect, useState, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";

import { errorMessage } from "../../api/client";
import {
  projectsApi,
  type ProjectBridges,
  type ProjectStatus,
  type WorkProject,
} from "../../api/work";
import { announce } from "../../lib/announce";
import { money, moneyInput, moneyToNumber } from "../../lib/format";
import { DateField } from "../DateField";
import { MoneyInput } from "../budget";
import { Tip } from "../help";
import { Alert, Button, Sheet } from "../ui";

/** Formulário para criar ou editar os dados gerais de um projeto. */
export function ProjectEditorSheet({
  open,
  bridges,
  editing,
  onClose,
  onSaved,
}: {
  open: boolean;
  bridges: ProjectBridges | undefined;
  editing: WorkProject | null;
  onClose: () => void;
  onSaved: (project: WorkProject) => void;
}) {
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [status, setStatus] = useState<ProjectStatus>("active");
  const [contactId, setContactId] = useState("");
  const [dealId, setDealId] = useState("");
  const [propId, setPropId] = useState("");
  const [budget, setBudget] = useState("");
  const [rate, setRate] = useState("");
  const [due, setDue] = useState("");
  const [budgetTagChoice, setBudgetTagChoice] = useState<string>("new");
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setName(editing?.name ?? "");
    setDesc(editing?.description ?? "");
    setStatus(editing?.status ?? "active");
    setContactId("");
    setDealId("");
    setPropId("");
    setBudget(editing ? moneyInput(editing.budget_value) : "");
    setRate(editing ? moneyInput(editing.hourly_rate) : "");
    setDue(editing?.due_date ?? "");
    setBudgetTagChoice("new");
    setErr(null);
  }, [open, editing]);

  const saveProject = useMutation({
    mutationFn: () => {
      const details = {
        name: name.trim(),
        due_date: due || null,
      };
      const budgetValue = moneyToNumber(budget);
      const hourlyRate = moneyToNumber(rate);
      if (editing) {
        return projectsApi.update(editing.id, {
          ...details,
          description: desc.trim() || null,
          budget_value: String(budgetValue),
          hourly_rate: String(hourlyRate),
        });
      }
      return projectsApi.create({
        ...details,
        description: desc.trim() || undefined,
        status,
        contact_id: contactId || null,
        crm_deal_id: dealId || null,
        proposal_id: propId || null,
        budget_project_id:
          budgetTagChoice !== "new" && budgetTagChoice !== "none" ? budgetTagChoice : null,
        budget_value: budgetValue,
        hourly_rate: hourlyRate,
        link_budget_tag: budgetTagChoice === "new",
      });
    },
    onSuccess: (saved) => {
      onSaved(saved);
      onClose();
      announce(editing ? "Projeto atualizado" : "Projeto criado");
    },
    onError: (e) => setErr(errorMessage(e)),
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) {
      setErr("Informe o nome do projeto.");
      return;
    }
    if (!saveProject.isPending) saveProject.mutate();
  }

  const previewBudget = moneyToNumber(budget);
  const previewRate = moneyToNumber(rate);
  const previewEstHours =
    previewRate > 0 && previewBudget > 0
      ? (previewBudget / previewRate).toFixed(1).replace(".", ",")
      : null;

  return (
    <Sheet open={open} title={editing ? "Editar projeto" : "Novo projeto"} onClose={onClose}>
      <form className="inline-form stack" onSubmit={submit}>
        {err && <Alert tone="error">{err}</Alert>}

        <label className="field">
          <span className="field-label">Nome do projeto</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            placeholder="Ex.: Implantação loja virtual"
          />
        </label>

        {!editing && <fieldset className="radios">
          <legend className="field-label">Etapa inicial</legend>
          <div className="segmented">
            <label>
              <input
                type="radio"
                name="proj-init-status"
                checked={status === "active"}
                onChange={() => setStatus("active")}
              />
              Em andamento
            </label>
            <label>
              <input
                type="radio"
                name="proj-init-status"
                checked={status === "planning"}
                onChange={() => setStatus("planning")}
              />
              Planejamento
            </label>
          </div>
        </fieldset>}

        <div className="grid-2">
          <label className="field">
            <span className="field-label">Prazo de entrega</span>
            <DateField value={due} onChange={setDue} label="Prazo de entrega" />
          </label>
          {!editing && <label className="field">
            <span className="field-label">Cliente (CRM)</span>
            <select value={contactId} onChange={(e) => setContactId(e.target.value)}>
              <option value="">Sem vínculo direto</option>
              {(bridges?.contacts ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>}
        </div>

        {!editing && <div className="grid-2">
          <label className="field">
            <span className="field-label">Negócio CRM (opcional)</span>
            <select value={dealId} onChange={(e) => setDealId(e.target.value)}>
              <option value="">Nenhum</option>
              {(bridges?.deals ?? []).map((d) => (
                <option key={d.id} value={d.id}>
                  {d.title} ({money(d.value)})
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field-label">Proposta / OS vinculada</span>
            <select
              value={propId}
              onChange={(e) => {
                const id = e.target.value;
                setPropId(id);
                const found = bridges?.proposals.find((x) => x.id === id);
                if (found) {
                  if (!name) setName(found.title);
                  if (!budget) setBudget(String(found.total_amount).replace(".", ","));
                }
              }}
            >
              <option value="">Nenhuma</option>
              {(bridges?.proposals ?? []).map((pr) => (
                <option key={pr.id} value={pr.id}>
                  #{String(pr.number).padStart(4, "0")} — {pr.title}
                </option>
              ))}
            </select>
          </label>
        </div>}

        <div className="grid-2">
          <label className="field">
            <span className="field-label">Valor orçado (R$)</span>
            <MoneyInput value={budget} onChange={setBudget} placeholder="0,00" required={false} />
          </label>
          <label className="field">
            <span className="field-label">Meta valor/hora (R$)</span>
            <MoneyInput value={rate} onChange={setRate} placeholder="0,00" required={false} />
          </label>
        </div>

        {previewEstHours && (
          <div className="summary-box">
            <div className="split small">
              <span>Estimativa pela meta/hora</span>
              <strong>{previewEstHours} h disponíveis dentro do orçamento</strong>
            </div>
          </div>
        )}

        {!editing && <label className="field">
          <span className="field-label">
            Etiqueta no Meu Orçamento (rentabilidade){" "}
            <Tip>Cria uma etiqueta exclusiva para não misturar despesas antigas, ou escolha uma já existente se quiser somar junto.</Tip>
          </span>
          <select
            value={budgetTagChoice}
            onChange={(e) => setBudgetTagChoice(e.target.value)}
          >
            <option value="new">Criar etiqueta exclusiva deste projeto (recomendado)</option>
            <option value="none">Não vincular etiqueta ao Orçamento</option>
            {(bridges?.budget_tags ?? []).map((tag) => (
              <option key={tag.id} value={tag.id}>
                Usar etiqueta existente: {tag.name}
              </option>
            ))}
          </select>
        </label>}

        <div className="field">
          <label htmlFor="proj-desc" className="field-label">
            Descrição / escopo (opcional)
          </label>
          <textarea
            id="proj-desc"
            rows={2}
            value={desc}
            onChange={(e) => setDesc(e.target.value)}
          />
        </div>

        <div className="form-actions">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" loading={saveProject.isPending}>
            {editing ? "Salvar projeto" : "Criar projeto"}
          </Button>
        </div>
      </form>
    </Sheet>
  );
}
