import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";

import {
  budgetApi,
  INTERVALS,
  keys,
  paymentLabel,
  useBudgetMutation,
  useCategories,
  type Category,
  type Interval,
  type Recurring,
} from "../api/budget";
import { errorMessage } from "../api/client";
import { CategorySelect, FormActions, MoneyInput, requireMoney } from "../components/budget";
import { Alert, PageHeader } from "../components/ui";
import { money, moneyInput, monthLabel } from "../lib/format";

function RecurringEdit({ item, categories, onDone }: { item: Recurring; categories: Category[]; onDone: () => void }) {
  const [description, setDescription] = useState(item.description);
  const [amount, setAmount] = useState(moneyInput(item.amount));
  const [categoryId, setCategoryId] = useState(item.category_id ?? "");
  const [dueDay, setDueDay] = useState(item.due_day ? String(item.due_day) : "");
  const [endMonth, setEndMonth] = useState(item.end_month ?? "");
  const [interval, setInterval] = useState<Interval>(item.interval_months ?? 1);
  const [error, setError] = useState("");
  const save = useBudgetMutation(() =>
    budgetApi.updateRecurring(item.id, {
      description,
      amount: requireMoney(amount),
      end_month: endMonth || null,
      ...(item.kind === "expense"
        ? { category_id: categoryId || null, due_day: dueDay ? Number(dueDay) : null, interval_months: interval }
        : {}),
    }),
  );

  return (
    <form
      className="inline-form"
      onSubmit={async (e) => {
        e.preventDefault();
        setError("");
        try {
          await save.mutateAsync(undefined);
          onDone();
        } catch (err) {
          setError(errorMessage(err));
        }
      }}
    >
      <Alert tone="error">{error}</Alert>
      <p className="muted small">
        As mudanças valem a partir do mês atual, nos lançamentos ainda não pagos.
      </p>
      <div className="grid-2">
        <label>
          Descrição
          <input value={description} onChange={(e) => setDescription(e.target.value)} required maxLength={120} />
        </label>
        <label>
          Valor
          <MoneyInput value={amount} onChange={setAmount} />
        </label>
        {item.kind === "expense" && (
          <>
            <label>
              Categoria
              <CategorySelect categories={categories} value={categoryId} onChange={setCategoryId} />
            </label>
            <label>
              Dia do vencimento
              <input type="number" min={1} max={31} value={dueDay} onChange={(e) => setDueDay(e.target.value)} />
            </label>
            <label>
              Frequência
              <select value={interval} onChange={(e) => setInterval(Number(e.target.value) as Interval)}>
                {INTERVALS.map((i) => (
                  <option key={i.value} value={i.value}>
                    {i.label}
                  </option>
                ))}
              </select>
            </label>
          </>
        )}
        <label>
          Último mês (opcional)
          <input type="month" value={endMonth} min={item.start_month} onChange={(e) => setEndMonth(e.target.value)} />
        </label>
      </div>
      <FormActions loading={save.isPending} onCancel={onDone} />
    </form>
  );
}

function RecurringRow({ item, categories }: { item: Recurring; categories: Category[] }) {
  const [editing, setEditing] = useState(false);
  const remove = useBudgetMutation(() => budgetApi.deleteRecurring(item.id));
  const category = categories.find((c) => c.id === item.category_id);

  if (editing) {
    return (
      <li>
        <RecurringEdit item={item} categories={categories} onDone={() => setEditing(false)} />
      </li>
    );
  }

  return (
    <li className="item">
      <button type="button" className="item__main" onClick={() => setEditing(true)} title="Editar">
        <span className="item__title">{item.description}</span>
        <span className="item__meta">
          {item.kind === "expense" ? (category?.name ?? "Sem categoria") : item.income_type === "variable" ? "Renda variável" : "Renda fixa"}
          {item.interval_months > 1 && ` · ${INTERVALS.find((i) => i.value === item.interval_months)?.label.toLowerCase()}`}
          {item.due_day && ` · dia ${item.due_day}`}
          {item.payment_method && ` · ${paymentLabel(item.payment_method)}`}
          {` · desde ${monthLabel(item.start_month, true)}`}
          {item.end_month && ` até ${monthLabel(item.end_month, true)}`}
        </span>
      </button>
      <span className="item__amount">{money(item.amount)}</span>
      <button
        type="button"
        className="icon-btn"
        aria-label="Excluir"
        title="Excluir"
        onClick={() =>
          window.confirm(
            `Excluir "${item.description}"? Os lançamentos do mês atual e anteriores serão mantidos; os dos próximos meses serão removidos.`,
          ) && remove.mutate(undefined)
        }
      >
        <Trash2 size={17} />
      </button>
    </li>
  );
}

export default function RecurringPage() {
  const items = useQuery({ queryKey: keys.recurring, queryFn: budgetApi.recurring });
  const categories = useCategories();
  const cats = categories.data ?? [];
  const incomes = items.data?.filter((i) => i.kind === "income") ?? [];
  const expenses = items.data?.filter((i) => i.kind === "expense") ?? [];

  return (
    <div className="stack">
      <PageHeader
        title="Contas e rendas fixas"
        subtitle={`Lançadas automaticamente todo mês. Para criar uma, marque "Todo mês" ao lançar no orçamento.`}
      />
      {items.isPending && <p className="muted">Carregando…</p>}
      {items.isError && <Alert tone="error">{errorMessage(items.error)}</Alert>}
      {items.data && (
        <div className="layout-2">
          <section className="card stack">
            <h2>Rendas fixas</h2>
            {incomes.length === 0 && <p className="muted">Nenhuma.</p>}
            <ul className="items">
              {incomes.map((item) => (
                <RecurringRow key={item.id} item={item} categories={cats} />
              ))}
            </ul>
          </section>
          <section className="card stack">
            <h2>Contas fixas</h2>
            {expenses.length === 0 && <p className="muted">Nenhuma.</p>}
            <ul className="items">
              {expenses.map((item) => (
                <RecurringRow key={item.id} item={item} categories={cats} />
              ))}
            </ul>
          </section>
        </div>
      )}
    </div>
  );
}
