import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";

import { budgetApi, useBudgetMutation, useCategories, type Category } from "../api/budget";
import { errorMessage } from "../api/client";
import { extrasApi, extrasKeys } from "../api/extras";
import { CategorySelect, FormActions, MoneyInput, requireMoney } from "../components/budget";
import { Tip } from "../components/help";
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
        <small className="muted">Alertas em 80% e ao exceder o limite.</small>
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
          window.confirm(`Excluir a categoria "${category.name}"? As despesas vinculadas ficarão sem categoria.`) &&
          remove.mutate(undefined)
        }
      >
        <Trash2 size={17} />
      </button>
    </li>
  );
}

function Rules() {
  const rules = useQuery({ queryKey: extrasKeys.rules, queryFn: extrasApi.rules });
  const categories = useCategories();
  const [pattern, setPattern] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [error, setError] = useState("");
  const create = useBudgetMutation(() => extrasApi.createRule(pattern, categoryId));
  const remove = useBudgetMutation((id: string) => extrasApi.deleteRule(id));
  const names = new Map((categories.data ?? []).map((c) => [c.id, c.name]));

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await create.mutateAsync(undefined);
      setPattern("");
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <section className="card stack">
      <h2>
        Regras automáticas{" "}
        <Tip>Quando a descrição tiver o texto, a categoria é escolhida sozinha: ao lançar, na sugestão e na importação do extrato.</Tip>
      </h2>
      <form className="row rule-form" onSubmit={submit}>
        <input value={pattern} onChange={(e) => setPattern(e.target.value)} placeholder="Se a descrição tiver… (ex.: uber)" aria-label="Texto da regra" required minLength={2} maxLength={60} />
        <CategorySelect categories={categories.data ?? []} value={categoryId} onChange={setCategoryId} label="Categoria da regra" />
        <Button type="submit" variant="secondary" loading={create.isPending} disabled={!categoryId}>
          Criar regra
        </Button>
      </form>
      <Alert tone="error">{error}</Alert>
      {rules.data && rules.data.length === 0 && (
        <p className="muted small" style={{ margin: 0 }}>
          Nenhuma regra cadastrada. Também é possível criar uma regra ao alterar a categoria de uma despesa.
        </p>
      )}
      <ul className="items">
        {rules.data?.map((r) => (
          <li key={r.id} className="item">
            <span className="item__main">
              <span className="item__title">contém “{r.pattern}”</span>
              <span className="item__meta">→ {names.get(r.category_id) ?? "?"}</span>
            </span>
            <button type="button" className="icon-btn" aria-label={`Excluir regra ${r.pattern}`} onClick={() => remove.mutate(r.id)}>
              <Trash2 size={16} />
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default function Categories() {
  const categories = useCategories();
  const [adding, setAdding] = useState(false);

  return (
    <div className="stack">
      <PageHeader
        title="Categorias"
        subtitle="Categorias essenciais entram como necessidades na regra 50/30/20. Limites mensais geram alertas."
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
      <Rules />
    </div>
  );
}
