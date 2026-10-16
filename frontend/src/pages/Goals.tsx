import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";

import { budgetApi, keys, useBudgetMutation, type Goal } from "../api/budget";
import { errorMessage } from "../api/client";
import { Bar, FormActions, MoneyInput, requireMoney } from "../components/budget";
import { Alert, Button } from "../components/ui";
import { money, moneyInput, percent, shortDate } from "../lib/format";

function monthsUntil(isoDate: string): number {
  const [y, m] = isoDate.split("-").map(Number);
  const now = new Date();
  return (y - now.getFullYear()) * 12 + (m - 1 - now.getMonth());
}

function GoalForm({ goal, onDone }: { goal?: Goal; onDone: () => void }) {
  const [name, setName] = useState(goal?.name ?? "");
  const [target, setTarget] = useState(goal ? moneyInput(goal.target_amount) : "");
  const [targetDate, setTargetDate] = useState(goal?.target_date ?? "");
  const [error, setError] = useState("");
  const save = useBudgetMutation(async () => {
    const data = { name, target_amount: requireMoney(target), target_date: targetDate || null };
    if (goal) await budgetApi.updateGoal(goal.id, data);
    else await budgetApi.createGoal(data);
  });

  async function submit(event: FormEvent) {
    event.preventDefault();
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
      <Alert tone="error">{error}</Alert>
      <div className="grid-2">
        <label>
          Nome da meta
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Reserva de emergência" required maxLength={80} autoFocus />
        </label>
        <label>
          Quanto quer juntar
          <MoneyInput value={target} onChange={setTarget} />
        </label>
        <label>
          Até quando (opcional)
          <input type="date" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} />
        </label>
      </div>
      <FormActions loading={save.isPending} onCancel={onDone} label={goal ? "Salvar" : "Criar meta"} />
    </form>
  );
}

function GoalCard({ goal }: { goal: Goal }) {
  const [editing, setEditing] = useState(false);
  const [amount, setAmount] = useState("");
  const [error, setError] = useState("");
  const contribute = useBudgetMutation((value: string) => budgetApi.contribute(goal.id, value));
  const remove = useBudgetMutation(() => budgetApi.deleteGoal(goal.id));

  const missing = Number(goal.target_amount) - Number(goal.current_amount);
  const months = goal.target_date ? monthsUntil(goal.target_date) : null;
  const perMonth = months && months > 0 && missing > 0 ? missing / months : null;

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

  if (editing) {
    return (
      <section className="card">
        <GoalForm goal={goal} onDone={() => setEditing(false)} />
      </section>
    );
  }

  return (
    <section className="card stack">
      <div className="section-header">
        <h2>{goal.name}</h2>
        <div className="row">
          <button type="button" className="link small" onClick={() => setEditing(true)}>
            Editar
          </button>
          <button
            type="button"
            className="link small tone--error"
            onClick={() => window.confirm(`Excluir a meta "${goal.name}"?`) && remove.mutate(undefined)}
          >
            Excluir
          </button>
        </div>
      </div>
      <div className="split">
        <span>
          <strong>{money(goal.current_amount)}</strong> <span className="muted">de {money(goal.target_amount)}</span>
        </span>
        <strong>{percent(goal.progress_pct)}</strong>
      </div>
      <Bar pct={goal.progress_pct} />
      <p className="muted small">
        {missing <= 0
          ? "Meta alcançada! 🎉"
          : `Faltam ${money(missing)}${goal.target_date ? ` até ${shortDate(goal.target_date)}/${goal.target_date.slice(0, 4)}` : ""}.`}
        {perMonth && ` Guardando ${money(perMonth)} por mês você chega lá.`}
      </p>
      <Alert tone="error">{error}</Alert>
      <div className="row">
        <div className="grow">
          <MoneyInput value={amount} onChange={setAmount} placeholder="Valor" label="Valor a guardar ou retirar da meta" />
        </div>
        <Button type="button" onClick={() => move(1)} loading={contribute.isPending}>
          Guardar
        </Button>
        <Button type="button" variant="secondary" onClick={() => move(-1)} disabled={contribute.isPending}>
          Retirar
        </Button>
      </div>
    </section>
  );
}

export default function Goals() {
  const goals = useQuery({ queryKey: keys.goals, queryFn: budgetApi.goals });
  const [adding, setAdding] = useState(false);

  return (
    <div className="stack">
      <div className="section-header">
        <h1>Metas</h1>
        {!adding && (
          <Button type="button" onClick={() => setAdding(true)}>
            + Nova meta
          </Button>
        )}
      </div>
      {adding && (
        <section className="card">
          <GoalForm onDone={() => setAdding(false)} />
        </section>
      )}
      {goals.isPending && <p className="muted">Carregando…</p>}
      {goals.isError && <Alert tone="error">{errorMessage(goals.error)}</Alert>}
      {goals.data?.length === 0 && !adding && (
        <p className="muted">Nenhuma meta ainda. Que tal começar por uma reserva de emergência?</p>
      )}
      {goals.data?.map((goal) => <GoalCard key={goal.id} goal={goal} />)}
    </div>
  );
}
