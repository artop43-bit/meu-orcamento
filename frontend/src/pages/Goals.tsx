import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { ImagePlus, Pencil, Plus, Star, Target, Trash2, X } from "lucide-react";

import { budgetApi, keys, useBudgetMutation, type Goal, type GoalKind } from "../api/budget";
import { errorMessage } from "../api/client";
import { checkImage, fileUrl, IMAGE_ACCEPT } from "../api/support";
import { Bar, MoneyInput, requireMoney } from "../components/budget";
import { DateField } from "../components/DateField";
import { EmptyGuide, Tip } from "../components/help";
import { Alert, Button, LoadingRegion, PageHeader, Sheet, Skeleton } from "../components/ui";
import { useUndo } from "../components/undo";
import { addMonths, money, moneyInput, monthLabel, parseMoney, percent, thisMonth } from "../lib/format";
import { GOAL_KINDS, goalKind, projectionText } from "../lib/goals";

type Plan = "date" | "monthly";

function monthsBetween(fromMonth: string, toIso: string): number {
  const [y1, m1] = fromMonth.split("-").map(Number);
  const [y2, m2] = toIso.split("-").map(Number);
  return (y2! - y1!) * 12 + (m2! - m1!);
}

/** Meta em duas etapas: objetivo (tipo, nome, motivação, imagem) e valor e prazo. */
function GoalForm({ goal, onDone }: { goal?: Goal; onDone: () => void }) {
  const [step, setStep] = useState(0);
  const [kind, setKind] = useState<GoalKind>(goal?.kind ?? "emergency");
  const [name, setName] = useState(goal?.name ?? "");
  const [motivation, setMotivation] = useState(goal?.motivation ?? "");
  const [image, setImage] = useState<File | null>(null);
  const [target, setTarget] = useState(goal ? moneyInput(goal.target_amount) : "");
  const [saved, setSaved] = useState("");
  const [plan, setPlan] = useState<Plan>(goal?.monthly_plan && !goal.target_date ? "monthly" : "date");
  const [targetDate, setTargetDate] = useState(goal?.target_date ?? "");
  const [monthly, setMonthly] = useState(goal?.monthly_plan ? moneyInput(goal.monthly_plan) : "");
  const [isMain, setIsMain] = useState(goal?.is_main ?? false);
  const [error, setError] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const preview = useMemo(() => (image ? URL.createObjectURL(image) : null), [image]);
  useEffect(() => () => (preview ? URL.revokeObjectURL(preview) : undefined), [preview]);

  const info = goalKind(kind);
  const remaining = Math.max(0, Number(parseMoney(target) ?? 0) - Number(parseMoney(saved) ?? 0) - Number(goal?.current_amount ?? 0));
  const months = targetDate ? Math.max(1, monthsBetween(thisMonth(), targetDate)) : null;
  const perMonth = plan === "date" && months && remaining > 0 ? remaining / months : null;
  const monthlyValue = Number(parseMoney(monthly) ?? 0);
  const eta = plan === "monthly" && monthlyValue > 0 && remaining > 0 ? addMonths(thisMonth(), Math.ceil(remaining / monthlyValue)) : null;

  const save = useBudgetMutation(async () => {
    const data = {
      name: name.trim(),
      kind,
      motivation: motivation.trim() || null,
      target_amount: requireMoney(target),
      target_date: plan === "date" ? targetDate || null : null,
      monthly_plan: plan === "monthly" ? (monthly.trim() ? requireMoney(monthly) : null) : null,
      is_main: isMain,
      ...(goal ? {} : { current_amount: saved.trim() ? requireMoney(saved) : "0" }),
    };
    const result = goal ? await budgetApi.updateGoal(goal.id, data) : await budgetApi.createGoal(data);
    if (image) await budgetApi.setGoalImage(result.id, image, image.name);
  });

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (step === 0) {
      setStep(1);
      return;
    }
    setError("");
    try {
      await save.mutateAsync(undefined);
      onDone();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <form className="inline-form" onSubmit={submit}>
      <ol className="steps steps--compact" aria-label="Etapas">
        {["Objetivo", "Valor e prazo"].map((label, i) => (
          <li key={label} className={i === step ? "is-current" : i < step ? "is-done" : undefined} aria-current={i === step ? "step" : undefined}>
            <span className="steps__number">{i + 1}</span>
            {label}
          </li>
        ))}
      </ol>
      <Alert tone="error">{error}</Alert>
      {step === 0 && (
        <>
          <fieldset className="radios">
            <legend className="field-label">Tipo de objetivo</legend>
            <div className="goal-kinds">
              {GOAL_KINDS.map((k) => (
                <label key={k.value} className={`goal-kind ${kind === k.value ? "is-active" : ""}`}>
                  <input type="radio" name="goal-kind" checked={kind === k.value} onChange={() => setKind(k.value)} />
                  <span className="goal-kind__icon" aria-hidden>
                    {k.icon}
                  </span>
                  {k.label}
                </label>
              ))}
            </div>
          </fieldset>
          <label>
            Nome da meta
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder={`Ex.: ${info.example}`} required maxLength={80} />
          </label>
          <label>
            <span className="field-label">
              Motivação (opcional) <Tip>Uma frase sobre por que este objetivo importa. Aparece no acompanhamento da meta.</Tip>
            </span>
            <input value={motivation} onChange={(e) => setMotivation(e.target.value)} maxLength={200} placeholder="Ex.: Voltar a correr sem dor" />
          </label>
          <div className="goal-image-pick">
            <span className="field-label">Imagem do objetivo (opcional)</span>
            {preview || goal?.image_id ? (
              <span className="goal-image-pick__preview">
                <img src={preview ?? fileUrl(goal!.image_id!)} alt="Imagem do objetivo" />
                {preview && (
                  <button type="button" className="icon-btn" aria-label="Remover imagem escolhida" onClick={() => setImage(null)}>
                    <X size={16} />
                  </button>
                )}
              </span>
            ) : null}
            <Button type="button" variant="secondary" onClick={() => input.current?.click()}>
              <ImagePlus size={16} /> {preview || goal?.image_id ? "Trocar imagem" : "Escolher imagem"}
            </Button>
            <input
              ref={input}
              type="file"
              hidden
              accept={IMAGE_ACCEPT}
              aria-label="Escolher imagem do objetivo"
              onChange={(e) => {
                const file = e.target.files?.[0];
                e.target.value = "";
                if (!file) return;
                const problem = checkImage(file, 8);
                if (problem) setError(problem);
                else setImage(file);
              }}
            />
          </div>
        </>
      )}
      {step === 1 && (
        <>
          <div className="grid-2">
            <label>
              Valor total
              <MoneyInput value={target} onChange={setTarget} />
            </label>
            {!goal && (
              <label>
                <span className="field-label">
                  Já guardado <Tip>Quanto já está separado para este objetivo. Pode ficar em branco.</Tip>
                </span>
                <MoneyInput value={saved} onChange={setSaved} required={false} placeholder="0,00" />
              </label>
            )}
          </div>
          <fieldset className="radios">
            <legend className="field-label">Como planejar</legend>
            <div className="segmented">
              <label>
                <input type="radio" name="goal-plan" checked={plan === "date"} onChange={() => setPlan("date")} />
                Tenho uma data
              </label>
              <label>
                <input type="radio" name="goal-plan" checked={plan === "monthly"} onChange={() => setPlan("monthly")} />
                Tenho um valor por mês
              </label>
            </div>
          </fieldset>
          {plan === "date" ? (
            <label className="narrow">
              Data desejada
              <DateField value={targetDate} min={`${thisMonth()}-01`} onChange={setTargetDate} />
            </label>
          ) : (
            <label className="narrow">
              Valor por mês
              <MoneyInput value={monthly} onChange={setMonthly} required={false} placeholder="Ex.: 500,00" />
            </label>
          )}
          {(perMonth || eta) && (
            <p className="summary-box" aria-live="polite">
              {perMonth ? (
                <>
                  Para concluir em <strong>{monthLabel(targetDate.slice(0, 7))}</strong>, guarde <strong>{money(perMonth)}</strong> por mês.
                </>
              ) : (
                <>
                  Com {money(monthlyValue)} por mês, conclusão prevista para <strong>{monthLabel(eta!)}</strong>.
                </>
              )}
            </p>
          )}
          <label className="check">
            <input type="checkbox" checked={isMain} onChange={(e) => setIsMain(e.target.checked)} />
            Meta principal (aparece em destaque no Orçamento)
          </label>
        </>
      )}
      <div className="form-actions">
        <Button type="button" variant="secondary" onClick={step === 0 ? onDone : () => setStep(0)}>
          {step === 0 ? "Cancelar" : "Voltar"}
        </Button>
        <Button type="submit" loading={save.isPending}>
          {step === 0 ? "Continuar" : goal ? "Salvar" : "Criar meta"}
        </Button>
      </div>
    </form>
  );
}

function GoalCard({ goal }: { goal: Goal }) {
  const [editing, setEditing] = useState(false);
  const [amount, setAmount] = useState("");
  const [error, setError] = useState("");
  const contribute = useBudgetMutation((value: string) => budgetApi.contribute(goal.id, value));
  const makeMain = useBudgetMutation(() => budgetApi.updateGoal(goal.id, { is_main: true }));
  const undo = useUndo();
  const info = goalKind(goal.kind);
  const projection = projectionText(goal);
  const done = goal.completed_at !== null;

  async function move(sign: 1 | -1) {
    setError("");
    try {
      const value = requireMoney(amount);
      await contribute.mutateAsync(sign === 1 ? value : `-${value}`);
      setAmount("");
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <section className={`card stack goal-card ${goal.is_main ? "goal-card--main" : ""}`}>
      <Sheet open={editing} title="Editar meta" onClose={() => setEditing(false)}>
        {editing && <GoalForm goal={goal} onDone={() => setEditing(false)} />}
      </Sheet>
      {goal.image_id && <img className="goal-card__image" src={fileUrl(goal.image_id)} alt="" loading="lazy" />}
      <div className="section-header">
        <span className="goal-card__title">
          <span className="kpi__icon" aria-hidden>
            {info.icon}
          </span>
          <span>
            <h2>{goal.name}</h2>
            <span className="muted small">
              {info.label}
              {goal.is_main && " · meta principal"}
            </span>
          </span>
        </span>
        <span className="row" style={{ gap: 0, flexWrap: "nowrap" }}>
          {!goal.is_main && !done && (
            <button type="button" className="icon-btn" aria-label={`Definir ${goal.name} como meta principal`} title="Definir como principal" onClick={() => makeMain.mutate(undefined)}>
              <Star size={16} />
            </button>
          )}
          <button type="button" className="icon-btn" aria-label={`Editar meta ${goal.name}`} title="Editar" onClick={() => setEditing(true)}>
            <Pencil size={16} />
          </button>
          <button
            type="button"
            className="icon-btn"
            aria-label={`Excluir meta ${goal.name}`}
            title="Excluir"
            onClick={() => undo.remove({ ids: [goal.id], message: `Meta "${goal.name}" excluída`, commit: () => budgetApi.deleteGoal(goal.id) })}
          >
            <Trash2 size={16} />
          </button>
        </span>
      </div>
      {goal.motivation && <p className="goal-card__motivation">“{goal.motivation}”</p>}
      <div className="split" style={{ alignItems: "baseline" }}>
        <span>
          <span className="kpi__value goal-card__amount">{money(goal.current_amount)}</span> <span className="muted">de {money(goal.target_amount)}</span>
        </span>
        <strong>{percent(goal.progress_pct)}</strong>
      </div>
      <Bar pct={goal.progress_pct} />
      {projection.text && <p className={`goal-status goal-status--${projection.tone}`}>{projection.text}</p>}
      {!done && (
        <>
          <Alert tone="error">{error}</Alert>
          <div className="goal-card__actions">
            <MoneyInput value={amount} onChange={setAmount} placeholder="Valor" label={`Valor a guardar ou retirar da meta ${goal.name}`} />
            <Button type="button" onClick={() => void move(1)} loading={contribute.isPending}>
              Guardar
            </Button>
            <Button type="button" variant="secondary" onClick={() => void move(-1)} disabled={contribute.isPending}>
              Retirar
            </Button>
          </div>
        </>
      )}
    </section>
  );
}

export default function Goals() {
  const goals = useQuery({ queryKey: keys.goals, queryFn: budgetApi.goals });
  const [adding, setAdding] = useState(false);
  const undo = useUndo();
  const list = (goals.data ?? []).filter((g) => !undo.isHidden(g.id));
  const active = list.filter((g) => !g.completed_at).sort((a, b) => Number(b.is_main) - Number(a.is_main));
  const completed = list.filter((g) => g.completed_at);
  const saved = active.reduce((s, g) => s + Number(g.current_amount), 0);
  const target = active.reduce((s, g) => s + Number(g.target_amount), 0);

  return (
    <>
      <PageHeader
        title="Metas"
        subtitle={active.length > 0 ? `${money(saved)} guardados de ${money(target)} nas metas em andamento` : "Objetivos com valor, prazo e acompanhamento do ritmo."}
        actions={
          <Button type="button" onClick={() => setAdding(true)}>
            <Plus size={16} /> Nova meta
          </Button>
        }
      />
      {goals.isPending && (
        <LoadingRegion label="Carregando as metas">
          <Skeleton height={200} />
        </LoadingRegion>
      )}
      {goals.isError && <Alert tone="error">{errorMessage(goals.error)}</Alert>}
      {goals.data && list.length === 0 && (
        <section className="card">
          <EmptyGuide
            icon={<Target size={22} />}
            title="Nenhuma meta cadastrada"
            text="Defina um objetivo (reserva de emergência, viagem, compra, tratamento de saúde) e acompanhe quanto falta e quando ele será concluído no ritmo atual."
            action={
              <Button type="button" onClick={() => setAdding(true)}>
                <Plus size={16} /> Criar primeira meta
              </Button>
            }
          />
        </section>
      )}
      <div className="grid-cards">
        {active.map((goal) => (
          <GoalCard key={goal.id} goal={goal} />
        ))}
      </div>
      {completed.length > 0 && (
        <section className="stack" style={{ marginTop: 24 }}>
          <h2>Concluídas</h2>
          <div className="grid-cards">
            {completed.map((goal) => (
              <GoalCard key={goal.id} goal={goal} />
            ))}
          </div>
        </section>
      )}
      <Sheet open={adding} title="Nova meta" onClose={() => setAdding(false)}>
        {adding && <GoalForm onDone={() => setAdding(false)} />}
      </Sheet>
    </>
  );
}
