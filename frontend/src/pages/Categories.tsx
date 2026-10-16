import { useState, type FormEvent } from "react";

import { budgetApi, useBudgetMutation, useCategories, type Category } from "../api/budget";
import { errorMessage } from "../api/client";
import { FormActions } from "../components/budget";
import { Alert, Button } from "../components/ui";

function CategoryForm({ category, onDone }: { category?: Category; onDone: () => void }) {
  const [name, setName] = useState(category?.name ?? "");
  const [essential, setEssential] = useState(category?.is_essential ?? false);
  const [color, setColor] = useState(category?.color ?? "#4e79a7");
  const [error, setError] = useState("");
  const save = useBudgetMutation(async () => {
    const data = { name, is_essential: essential, color };
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
        <span className="item__meta">{category.is_essential ? "Essencial" : "Não essencial"}</span>
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
        ✕
      </button>
    </li>
  );
}

export default function Categories() {
  const categories = useCategories();
  const [adding, setAdding] = useState(false);

  return (
    <div className="stack">
      <div className="section-header">
        <h1>Categorias</h1>
        {!adding && (
          <Button type="button" onClick={() => setAdding(true)}>
            + Categoria
          </Button>
        )}
      </div>
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
