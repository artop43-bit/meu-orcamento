import { useState, type FormEvent } from "react";
import { Plus, Trash2 } from "lucide-react";

import { budgetApi, useBudgetMutation, useCategories, type Category } from "../api/budget";
import { errorMessage } from "../api/client";
import { FormActions, MoneyInput, requireMoney } from "../components/budget";
import { Alert, Button, PageHeader } from "../components/ui";
import { money, moneyInput } from "../lib/format";

function CategoryForm({ category, onDone }: { category?: Category; onDone: () => void }) {
  const [name, setName] = useState(category?.name ?? "");
  const [essential, setEssential] = useState(category?.is_essential ?? false);
  const [color, setColor] = useState(category?.color ?? "#4e79a7");
  const [limit, setLimit] = useState(category?.monthly_limit ? moneyInput(category.monthly_limit) : "");
  const [error, setError] = useState("");
  const save = useBudgetMutation(async () => {
    const data = { name, is_essential: essential, color, monthly_limit: limit.trim() ? requireMoney(limit) : null };
    if (category) await budgetApi.updateCategory(category.id, data);
    else await budgetApi.createCategory(data);
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
      <div className="row">
        <input type="color" value={color} onChange={(e) => setColor(e.target.value)} aria-label="Cor" className="color" />
        <input className="grow" value={name} onChange={(e) => setName(e.target.value)} placeholder="Nome" required maxLength={60} autoFocus aria-label="Nome" />
      </div>
      <label className="check">
        <input type="checkbox" checked={essential} onChange={(e) => setEssential(e.target.checked)} />
        Gasto essencial (moradia, alimentação, saúde…)
      </label>
      <label>
        Limite por mês (opcional)
        <span className="limit-input">
          <MoneyInput value={limit} onChange={setLimit} />
        </span>
        <small className="muted">Você recebe um alerta ao chegar em 80% e ao passar do limite.</small>
      </label>
      <FormActions loading={save.isPending} onCancel={onDone} />
    </form>
  );
}

function CategoryRow({ category }: { category: Category }) {
  const [editing, setEditing] = useState(false);
  const remove = useBudgetMutation(() => budgetApi.deleteCategory(category.id));

  if (editing) {
    return (
      <li>
        <CategoryForm category={category} onDone={() => setEditing(false)} />
      </li>
    );
  }
  return (
    <li className="item">
      <button type="button" className="item__main" onClick={() => setEditing(true)} title="Editar">
        <span className="item__title">
          <span className="dot" style={{ background: category.color ?? undefined }} aria-hidden /> {category.name}
        </span>
        <span className="item__meta">
          {category.is_essential ? "Essencial" : "Não essencial"}
          {category.monthly_limit && ` · limite de ${money(category.monthly_limit)} por mês`}
        </span>
      </button>
      <button
        type="button"
        className="icon-btn"
        aria-label="Excluir"
        title="Excluir"
        onClick={() =>
          window.confirm(`Excluir a categoria "${category.name}"? As contas dela ficarão sem categoria.`) &&
          remove.mutate(undefined)
        }
      >
        <Trash2 size={17} />
      </button>
    </li>
  );
}

export default function Categories() {
  const categories = useCategories();
  const [adding, setAdding] = useState(false);

  return (
    <div className="stack">
      <PageHeader
        title="Categorias"
        subtitle="Essenciais contam como necessidades na regra 50/30/20. Defina limites para receber alertas antes de estourar."
        actions={
          !adding && (
            <Button type="button" onClick={() => setAdding(true)}>
              <Plus size={16} /> Nova categoria
            </Button>
          )
        }
      />
      {categories.isError && <Alert tone="error">{errorMessage(categories.error)}</Alert>}
      <section className="card stack">
        {adding && <CategoryForm onDone={() => setAdding(false)} />}
        <ul className="items">
          {categories.data?.map((c) => (
            <CategoryRow key={c.id} category={c} />
          ))}
        </ul>
      </section>
    </div>
  );
}
