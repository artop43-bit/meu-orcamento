import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router";

import {
  budgetApi,
  useBudgetMutation,
  useCategories,
  useMonth,
  type Category,
  type Expense,
  type ExpenseInput,
  type Income,
  type MonthData,
} from "../api/budget";
import { errorMessage } from "../api/client";
import {
  Badge,
  Bar,
  CategorySelect,
  DeleteControl,
  FormActions,
  MoneyInput,
  SectionHeader,
  Stat,
  requireMoney,
} from "../components/budget";
import { Alert, Button } from "../components/ui";
import { addMonths, money, moneyInput, monthLabel, percent, shortDate, thisMonth, todayISO } from "../lib/format";

// ---------------------------------------------------------------- resumo

function Summary({ data }: { data: MonthData }) {
  const s = data.summary;
  const balance = Number(s.balance);
  const committed = s.committed_pct ?? 0;
  return (
    <section className="card stack">
      <div className="stats">
        <Stat label="Renda" value={money(s.income_total)} />
        <Stat label="Contas" value={money(s.expense_total)} />
        <Stat label="Saldo" value={money(s.balance)} tone={balance < 0 ? "error" : "ok"} />
        <Stat label="Comprometido" value={percent(s.committed_pct)} tone={committed > 100 ? "error" : undefined} />
      </div>
      {Number(s.expense_total) > 0 && (
        <div className="stack stack--tight">
          <div className="split">
            <span>
              Pago <strong>{money(s.paid_total)}</strong>
            </span>
            <span>
              A pagar <strong>{money(s.pending_total)}</strong>
            </span>
          </div>
          <Bar pct={(Number(s.paid_total) / Number(s.expense_total)) * 100} />
        </div>
      )}
    </section>
  );
}

function CategoryBreakdown({ data, categories }: { data: MonthData; categories: Category[] }) {
  const s = data.summary;
  const total = Number(s.expense_total);
  if (total === 0) return null;
  const colors = new Map(categories.map((c) => [c.id, c.color ?? undefined]));
  return (
    <section className="card stack">
      <h2>Para onde vai o dinheiro</h2>
      <div className="split muted">
        <span>
          Essencial <strong>{money(s.essential_total)}</strong>
        </span>
        <span>
          Não essencial <strong>{money(s.non_essential_total)}</strong>
        </span>
      </div>
      <ul className="breakdown">
        {s.by_category.map((c) => (
          <li key={c.category_id ?? "none"}>
            <div className="split">
              <span>{c.name}</span>
              <span>
                {money(c.total)} <span className="muted">· {percent(Math.round((Number(c.total) / total) * 1000) / 10)}</span>
              </span>
            </div>
            <Bar pct={(Number(c.total) / total) * 100} color={c.category_id ? colors.get(c.category_id) : undefined} />
          </li>
        ))}
      </ul>
    </section>
  );
}

// ---------------------------------------------------------------- rendas

function IncomeForm({ month, onDone }: { month: string; onDone: () => void }) {
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState("");
  const [everyMonth, setEveryMonth] = useState(false);
  const [error, setError] = useState("");
  const save = useBudgetMutation(async () => {
    const value = requireMoney(amount);
    if (everyMonth) {
      await budgetApi.createRecurring({ kind: "income", description, amount: value, start_month: month });
    } else {
      await budgetApi.createIncome(month, { description, amount: value });
    }
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
          Descrição
          <input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Salário" required maxLength={120} autoFocus />
        </label>
        <label>
          Valor
          <MoneyInput value={amount} onChange={setAmount} />
        </label>
      </div>
      <label className="check">
        <input type="checkbox" checked={everyMonth} onChange={(e) => setEveryMonth(e.target.checked)} />
        Recebo todo mês (renda fixa)
      </label>
      <FormActions loading={save.isPending} onCancel={onDone} label="Adicionar" />
    </form>
  );
}

function IncomeRow({ income }: { income: Income }) {
  const [editing, setEditing] = useState(false);
  const [description, setDescription] = useState(income.description);
  const [amount, setAmount] = useState(moneyInput(income.amount));
  const [error, setError] = useState("");
  const update = useBudgetMutation(() =>
    budgetApi.updateIncome(income.id, { description, amount: requireMoney(amount) }),
  );
  const remove = useBudgetMutation((scope: "one" | "following") => budgetApi.deleteIncome(income.id, scope));

  if (editing) {
    return (
      <li>
        <form
          className="inline-form"
          onSubmit={async (e) => {
            e.preventDefault();
            setError("");
            try {
              await update.mutateAsync(undefined);
              setEditing(false);
            } catch (err) {
              setError(errorMessage(err));
            }
          }}
        >
          <Alert tone="error">{error}</Alert>
          <div className="grid-2">
            <input value={description} onChange={(e) => setDescription(e.target.value)} required maxLength={120} aria-label="Descrição" />
            <MoneyInput value={amount} onChange={setAmount} />
          </div>
          <FormActions loading={update.isPending} onCancel={() => setEditing(false)} />
        </form>
      </li>
    );
  }

  return (
    <li className="item">
      <button type="button" className="item__main" onClick={() => setEditing(true)} title="Editar">
        <span className="item__title">{income.description}</span>
      </button>
      {income.recurring_id && (
        <span className="item__badges">
          <Badge>fixa</Badge>
        </span>
      )}
      <span className="item__amount">{money(income.amount)}</span>
      <DeleteControl
        repeats={income.recurring_id !== null}
        repeatLabel="Esta e as próximas"
        onDelete={(scope) => remove.mutateAsync(scope)}
      />
    </li>
  );
}

// ---------------------------------------------------------------- contas

type ExpenseKind = "single" | "installments" | "recurring";

function ExpenseForm({ month, categories, onDone }: { month: string; categories: Category[]; onDone: () => void }) {
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [kind, setKind] = useState<ExpenseKind>("single");
  const [installments, setInstallments] = useState("2");
  const [error, setError] = useState("");

  const save = useBudgetMutation(async () => {
    const value = requireMoney(amount);
    const category_id = categoryId || null;
    if (kind === "recurring") {
      await budgetApi.createRecurring({
        kind: "expense",
        description,
        amount: value,
        category_id,
        due_day: dueDate ? Number(dueDate.split("-")[2]) : null,
        start_month: month,
      });
      return;
    }
    const data: ExpenseInput = { description, amount: value, category_id, due_date: dueDate || null };
    if (kind === "installments") data.installments = Number(installments);
    await budgetApi.createExpense(month, data);
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
          Descrição
          <input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Aluguel" required maxLength={120} autoFocus />
        </label>
        <label>
          {kind === "installments" ? "Valor de cada parcela" : "Valor"}
          <MoneyInput value={amount} onChange={setAmount} />
        </label>
        <label>
          Categoria
          <CategorySelect categories={categories} value={categoryId} onChange={setCategoryId} />
        </label>
        <label>
          {kind === "recurring" ? "Vence no dia (escolha uma data)" : "Vencimento"}
          <input type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
        </label>
      </div>
      <fieldset className="radios">
        <legend className="sr-only">Tipo de conta</legend>
        <label className="check">
          <input type="radio" name="kind" checked={kind === "single"} onChange={() => setKind("single")} />
          Só neste mês
        </label>
        <label className="check">
          <input type="radio" name="kind" checked={kind === "installments"} onChange={() => setKind("installments")} />
          Parcelada
        </label>
        <label className="check">
          <input type="radio" name="kind" checked={kind === "recurring"} onChange={() => setKind("recurring")} />
          Todo mês (conta fixa)
        </label>
      </fieldset>
      {kind === "installments" && (
        <label className="narrow">
          Número de parcelas
          <input type="number" min={2} max={120} value={installments} onChange={(e) => setInstallments(e.target.value)} required />
        </label>
      )}
      <FormActions loading={save.isPending} onCancel={onDone} label="Adicionar" />
    </form>
  );
}

function ExpenseEdit({ expense, categories, onDone }: { expense: Expense; categories: Category[]; onDone: () => void }) {
  const [description, setDescription] = useState(expense.description);
  const [amount, setAmount] = useState(moneyInput(expense.amount));
  const [categoryId, setCategoryId] = useState(expense.category_id ?? "");
  const [dueDate, setDueDate] = useState(expense.due_date ?? "");
  const [error, setError] = useState("");
  const update = useBudgetMutation(() =>
    budgetApi.updateExpense(expense.id, {
      description,
      amount: requireMoney(amount),
      category_id: categoryId || null,
      due_date: dueDate || null,
    }),
  );

  return (
    <form
      className="inline-form"
      onSubmit={async (e) => {
        e.preventDefault();
        setError("");
        try {
          await update.mutateAsync(undefined);
          onDone();
        } catch (err) {
          setError(errorMessage(err));
        }
      }}
    >
      <Alert tone="error">{error}</Alert>
      {expense.recurring_id && (
        <p className="muted small">Isto altera só este mês. Para mudar todos os meses, edite em Contas fixas.</p>
      )}
      <div className="grid-2">
        <input value={description} onChange={(e) => setDescription(e.target.value)} required maxLength={120} aria-label="Descrição" />
        <MoneyInput value={amount} onChange={setAmount} />
        <CategorySelect categories={categories} value={categoryId} onChange={setCategoryId} />
        <input type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} aria-label="Vencimento" />
      </div>
      <FormActions loading={update.isPending} onCancel={onDone} />
    </form>
  );
}

function ExpenseRow({ expense, categories }: { expense: Expense; categories: Category[] }) {
  const [editing, setEditing] = useState(false);
  const togglePaid = useBudgetMutation((paid: boolean) => budgetApi.updateExpense(expense.id, { paid }));
  const remove = useBudgetMutation((scope: "one" | "following") => budgetApi.deleteExpense(expense.id, scope));
  const category = categories.find((c) => c.id === expense.category_id);
  const overdue = !expense.paid && expense.due_date !== null && expense.due_date < todayISO();

  if (editing) {
    return (
      <li>
        <ExpenseEdit expense={expense} categories={categories} onDone={() => setEditing(false)} />
      </li>
    );
  }

  return (
    <li className={`item ${expense.paid ? "item--paid" : ""}`}>
      <input
        type="checkbox"
        className="item__check"
        checked={expense.paid}
        disabled={togglePaid.isPending}
        onChange={(e) => togglePaid.mutate(e.target.checked)}
        aria-label={expense.paid ? "Marcar como não paga" : "Marcar como paga"}
      />
      <button type="button" className="item__main" onClick={() => setEditing(true)} title="Editar">
        <span className="item__title">{expense.description}</span>
        <span className="item__meta">
          {category && (
            <span className="dot" style={{ background: category.color ?? undefined }} aria-hidden />
          )}
          {category?.name ?? "Sem categoria"}
          {expense.due_date && (
            <span className={overdue ? "tone--error" : undefined}>
              {" · vence "}
              {shortDate(expense.due_date)}
              {overdue && " (atrasada)"}
            </span>
          )}
        </span>
      </button>
      <span className="item__badges">
        {expense.installment_total && (
          <Badge tone="accent">
            {expense.installment_number}/{expense.installment_total}
          </Badge>
        )}
        {expense.recurring_id && <Badge>fixa</Badge>}
      </span>
      <span className="item__amount">{money(expense.amount)}</span>
      <DeleteControl
        repeats={expense.installment_group_id !== null || expense.recurring_id !== null}
        repeatLabel={expense.installment_group_id ? "Esta e as próximas parcelas" : "Esta e as próximas"}
        onDelete={(scope) => remove.mutateAsync(scope)}
      />
    </li>
  );
}

// ---------------------------------------------------------------- página

export default function MonthPage() {
  const params = useParams();
  const month = params.month && /^\d{4}-\d{2}$/.test(params.month) ? params.month : thisMonth();
  const data = useMonth(month);
  const categories = useCategories();
  const [adding, setAdding] = useState<"income" | "expense" | null>(null);

  const cats = categories.data ?? [];

  return (
    <div className="stack">
      <div className="month-nav">
        <Link className="icon-btn" to={`/orcamento/${addMonths(month, -1)}`} aria-label="Mês anterior">
          ‹
        </Link>
        <h1>{monthLabel(month)}</h1>
        <Link className="icon-btn" to={`/orcamento/${addMonths(month, 1)}`} aria-label="Próximo mês">
          ›
        </Link>
        {month !== thisMonth() && (
          <Link className="link small" to={`/orcamento/${thisMonth()}`}>
            Ir para o mês atual
          </Link>
        )}
      </div>

      {data.isPending && <p className="muted">Carregando…</p>}
      {data.isError && <Alert tone="error">{errorMessage(data.error)}</Alert>}

      {data.data && (
        <>
          <Summary data={data.data} />

          <section className="card stack">
            <SectionHeader
              title="Renda"
              total={data.data.summary.income_total}
              action={
                adding !== "income" && (
                  <Button type="button" variant="secondary" onClick={() => setAdding("income")}>
                    + Renda
                  </Button>
                )
              }
            />
            {adding === "income" && <IncomeForm month={month} onDone={() => setAdding(null)} />}
            {data.data.incomes.length === 0 && adding !== "income" && (
              <p className="muted">Nenhuma renda lançada neste mês.</p>
            )}
            <ul className="items">
              {data.data.incomes.map((income) => (
                <IncomeRow key={income.id} income={income} />
              ))}
            </ul>
          </section>

          <section className="card stack">
            <SectionHeader
              title="Contas"
              total={data.data.summary.expense_total}
              action={
                adding !== "expense" && (
                  <Button type="button" variant="secondary" onClick={() => setAdding("expense")}>
                    + Conta
                  </Button>
                )
              }
            />
            {adding === "expense" && (
              <ExpenseForm month={month} categories={cats} onDone={() => setAdding(null)} />
            )}
            {data.data.expenses.length === 0 && adding !== "expense" && (
              <p className="muted">Nenhuma conta lançada neste mês.</p>
            )}
            <ul className="items">
              {data.data.expenses.map((expense) => (
                <ExpenseRow key={expense.id} expense={expense} categories={cats} />
              ))}
            </ul>
          </section>

          <CategoryBreakdown data={data.data} categories={cats} />
        </>
      )}
    </div>
  );
}
