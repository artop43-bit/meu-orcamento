import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { useQueryClient } from "@tanstack/react-query";
import {
  ArrowDownLeft,
  CalendarClock,
  ChevronLeft,
  ChevronRight,
  Copy,
  Gauge,
  Search,
  Pencil,
  Plus,
  Receipt,
  Scale,
  Trash2,
  Repeat,
  Sparkles,
  Wallet,
} from "lucide-react";
import { Link, useParams } from "react-router";

import {
  budgetApi,
  keys,
  useBudgetMutation,
  useCategories,
  useMonth,
  paymentLabel,
  type Category,
  type DeleteScope,
  type Expense,
  type Income,
  type MonthData,
} from "../api/budget";
import { errorMessage } from "../api/client";
import { announce } from "../lib/announce";
import { haptic } from "../lib/haptics";
import { Badge, Bar } from "../components/budget";
import { ExpenseForm, IncomeForm, type ExpenseDraft } from "../components/entryForms";
import { EmptyGuide, Tip } from "../components/help";
import { ConsultantTeaser } from "../components/consultant";
import { Alert, Button, Kpi, LoadingRegion, PageHeader, Sheet, Skeleton } from "../components/ui";
import { useUndo } from "../components/undo";
import { addMonths, money, monthLabel, percent, shortDate, thisMonth, todayISO } from "../lib/format";
import { normalizeText } from "../lib/text";

type Editing =
  | { type: "new-expense"; draft?: ExpenseDraft }
  | { type: "new-income" }
  | { type: "expense"; expense: Expense }
  | { type: "income"; income: Income }
  | { type: "delete-expense"; expense: Expense }
  | { type: "choose" }
  | null;

// ---------------------------------------------------------------- indicadores

function Kpis({ data }: { data: MonthData }) {
  const s = data.summary;
  const balance = Number(s.balance);
  const committed = s.committed_pct;
  const expenseTotal = Number(s.expense_total);
  const paidPct = expenseTotal > 0 ? (Number(s.paid_total) / expenseTotal) * 100 : 0;
  return (
    <div className="kpis">
      <Kpi icon={<ArrowDownLeft size={17} />} label="Renda" value={money(s.income_total)} foot={`${data.incomes.length} lançamento(s)`} />
      <Kpi
        icon={<Receipt size={17} />}
        tone="expense"
        label="Contas"
        value={money(s.expense_total)}
        foot={
          <span className="stack stack--tight" style={{ gap: 6 }}>
            <Bar pct={paidPct} />
            <span>
              Pago {money(s.paid_total)} · falta {money(s.pending_total)}
            </span>
          </span>
        }
      />
      <Kpi
        icon={<Scale size={17} />}
        tone={balance < 0 ? "expense" : "accent"}
        label="Saldo"
        value={money(s.balance)}
        valueClass={balance < 0 ? "tone--error" : "tone--ok"}
        foot={balance < 0 ? "As contas passam da renda" : "Sobra depois das contas"}
      />
      <Kpi
        icon={<Gauge size={17} />}
        tone="neutral"
        label="Renda comprometida"
        value={percent(committed)}
        valueClass={committed !== null && committed > 100 ? "tone--error" : undefined}
        foot={committed === null ? "Sem renda lançada" : committed <= 50 ? "Saudável (até 50%)" : committed <= 80 ? "Atenção" : "Alto"}
      />
    </div>
  );
}

// ---------------------------------------------------------------- contas

function statusOf(expense: Expense): { label: string; tone: "ok" | "warn" | "error" } {
  if (expense.paid) return { label: "Paga", tone: "ok" };
  if (expense.due_date && expense.due_date < todayISO()) return { label: "Atrasada", tone: "error" };
  return { label: "A pagar", tone: "warn" };
}

function LedgerRow({
  expense,
  category,
  onEdit,
  onDelete,
  onDuplicate,
}: {
  expense: Expense;
  category: Category | undefined;
  onEdit: () => void;
  onDelete: () => void;
  onDuplicate: () => void;
}) {
  const toggle = useBudgetMutation((paid: boolean) => budgetApi.updateExpense(expense.id, { paid }));
  // Resposta imediata: mostra o novo estado enquanto o servidor confirma.
  const paid = toggle.isPending && toggle.variables !== undefined ? toggle.variables : expense.paid;
  const status = statusOf({ ...expense, paid });

  function onToggle(next: boolean) {
    haptic(next ? "success" : "tap");
    toggle.mutate(next, {
      onSuccess: () => announce(`${expense.description}: ${next ? "paga" : "a pagar"}`),
      onError: (err) => {
        haptic("error");
        announce(`Não foi possível salvar: ${errorMessage(err)}`);
      },
    });
  }

  return (
    <li className={`ledger__row ${paid ? "ledger__row--paid" : ""}`} aria-busy={toggle.isPending || undefined}>
      <label className="ledger__check">
        <input
          type="checkbox"
          className="item__check"
          checked={paid}
          onChange={(e) => onToggle(e.target.checked)}
          aria-label={`${expense.description} paga`}
        />
      </label>
      <button type="button" className="ledger__open ledger__desc" onClick={onEdit} title="Editar">
        <span className="ledger__title">
          <span>{expense.description}</span>
          {expense.installment_total && (
            <Badge tone="accent">
              {expense.installment_number}/{expense.installment_total}
            </Badge>
          )}
          {expense.recurring_id && <Badge>fixa</Badge>}
        </span>
        <span className="ledger__sub">
          <span className="dot" style={{ background: category?.color ?? undefined }} aria-hidden />
          {category?.name ?? "Sem categoria"}
          {" · "}
          {expense.due_date ? `vence ${shortDate(expense.due_date)}` : "sem vencimento"}
          {expense.payment_method && ` · ${paymentLabel(expense.payment_method)}`}
          {expense.notes && <span title={expense.notes}> · 📝</span>}
        </span>
      </button>
      <span className="ledger__status">
        <span className={`badge badge--${status.tone}`}>{status.label}</span>
      </span>
      <span className="ledger__amount">{money(expense.amount)}</span>
      <span className="ledger__actions">
        <button type="button" className="icon-btn" aria-label={`Editar ${expense.description}`} title="Editar" onClick={onEdit}>
          <Pencil size={16} />
        </button>
        <button type="button" className="icon-btn" aria-label={`Duplicar ${expense.description}`} title="Duplicar" onClick={onDuplicate}>
          <Copy size={16} />
        </button>
        <button type="button" className="icon-btn" aria-label={`Excluir ${expense.description}`} title="Excluir" onClick={onDelete}>
          <Trash2 size={16} />
        </button>
      </span>
    </li>
  );
}

function ExpensesCard({
  data,
  categories,
  setEditing,
}: {
  data: MonthData;
  categories: Category[];
  setEditing: (e: Editing) => void;
}) {
  const undo = useUndo();
  const byId = new Map(categories.map((c) => [c.id, c]));
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [categoryFilter, setCategoryFilter] = useState("");
  const filtering = query.trim() !== "" || status !== "all" || categoryFilter !== "";
  const visible = useMemo(() => {
    const q = normalizeText(query);
    const today = todayISO();
    return data.expenses.filter((e) => {
      if (undo.isHidden(e.id)) return false;
      if (q && !normalizeText(`${e.description} ${e.notes ?? ""}`).includes(q)) return false;
      if (categoryFilter && (e.category_id ?? "none") !== categoryFilter) return false;
      if (status === "paid") return e.paid;
      if (status === "pending") return !e.paid;
      if (status === "late") return !e.paid && !!e.due_date && e.due_date < today;
      return true;
    });
  }, [data.expenses, query, status, categoryFilter, undo]);
  const visibleTotal = visible.reduce((sum, e) => sum + Number(e.amount), 0);
  return (
    <section className="card stack">
      <div className="section-header">
        <h2>
          Contas <span className="muted section-header__total">· {money(data.summary.expense_total)}</span>
        </h2>
        <Button type="button" variant="secondary" className="only-desktop" onClick={() => setEditing({ type: "new-expense" })}>
          <Plus size={16} /> Conta
        </Button>
      </div>
      {data.expenses.length > 3 && (
        <div className="list-tools" role="search">
          <label className="list-tools__search">
            <Search size={16} aria-hidden />
            <span className="sr-only">Buscar conta</span>
            <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Buscar (ex.: mercado)" />
          </label>
          <select value={status} onChange={(e) => setStatus(e.target.value as StatusFilter)} aria-label="Filtrar por situação">
            <option value="all">Todas</option>
            <option value="pending">A pagar</option>
            <option value="late">Atrasadas</option>
            <option value="paid">Pagas</option>
          </select>
          <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)} aria-label="Filtrar por categoria">
            <option value="">Todas as categorias</option>
            <option value="none">Sem categoria</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>
      )}
      {filtering && (
        <p className="muted small" style={{ margin: 0 }} role="status">
          {visible.length} de {data.expenses.length} conta(s) · {money(visibleTotal)}{" "}
          <button
            type="button"
            className="link-btn"
            onClick={() => {
              setQuery("");
              setStatus("all");
              setCategoryFilter("");
            }}
          >
            Limpar filtros
          </button>
        </p>
      )}
      {data.expenses.length === 0 ? (
        <EmptyGuide
          icon={<Receipt size={22} />}
          title="Nenhuma conta neste mês"
          text="Lance o que você paga: contas da casa, compras, assinaturas. Dá para marcar como paga, parcelar e repetir."
          example={<>Ex.: “Aluguel” R$ 1.200 vence dia 10 · “Mercado” R$ 350 já pago · “TV” 10x de R$ 199</>}
          action={
            <Button type="button" onClick={() => setEditing({ type: "new-expense" })}>
              <Plus size={16} /> Lançar conta
            </Button>
          }
        />
      ) : (
        <ul className="ledger">
          <li className="ledger__head" aria-hidden>
            <span />
            <span>Descrição</span>
            <span>Situação</span>
            <span style={{ textAlign: "right" }}>Valor</span>
            <span />
          </li>
          {visible.map((expense) => (
              <LedgerRow
                key={expense.id}
                expense={expense}
                category={expense.category_id ? byId.get(expense.category_id) : undefined}
                onEdit={() => setEditing({ type: "expense", expense })}
                onDuplicate={() =>
                  setEditing({
                    type: "new-expense",
                    draft: {
                      description: expense.description,
                      amount: expense.amount,
                      category_id: expense.category_id,
                      payment_method: expense.payment_method,
                      notes: expense.notes,
                    },
                  })
                }
                onDelete={() =>
                  // Conta avulsa: exclui na hora (com Desfazer). Parcelada ou fixa: pergunta o alcance.
                  expense.installment_group_id || expense.recurring_id
                    ? setEditing({ type: "delete-expense", expense })
                    : removeExpense(undo, expense, "one")
                }
              />
            ))}
        </ul>
      )}
    </section>
  );
}

type StatusFilter = "all" | "pending" | "late" | "paid";

// ---------------------------------------------------------------- renda e categorias (coluna lateral)

function IncomeGroup({ title, items, setEditing }: { title: string; items: Income[]; setEditing: (e: Editing) => void }) {
  if (items.length === 0) return null;
  const total = items.reduce((sum, i) => sum + Number(i.amount), 0);
  return (
    <div className="stack stack--tight">
      <div className="split small">
        <strong>{title}</strong>
        <span className="num muted">{money(total)}</span>
      </div>
      <ul className="items">
        {items.map((income) => (
          <li key={income.id} className="item">
            <button type="button" className="item__main" onClick={() => setEditing({ type: "income", income })} title="Editar">
              <span className="item__title">{income.description}</span>
              <span className="item__meta">
                {[income.recurring_id ? "Todo mês" : null, income.day ? `dia ${income.day}` : null, income.notes ? "📝" : null]
                  .filter(Boolean)
                  .join(" · ")}
              </span>
            </button>
            <span className="item__amount tone--ok">{money(income.amount)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function IncomesCard({ data, setEditing }: { data: MonthData; setEditing: (e: Editing) => void }) {
  const undo = useUndo();
  const incomes = data.incomes.filter((income) => !undo.isHidden(income.id));
  const fixed = incomes.filter((i) => i.income_type !== "variable");
  const variable = incomes.filter((i) => i.income_type === "variable");
  return (
    <section className="card stack">
      <div className="section-header">
        <h2>
          Renda <span className="muted section-header__total">· {money(data.summary.income_total)}</span>
          <Tip label="O que é renda fixa e variável">
            Fixa: o mesmo valor todo mês (salário). Variável: muda a cada mês (bicos, comissões). A previsão usa a média da variável.
          </Tip>
        </h2>
        <Button type="button" variant="secondary" className="only-desktop" onClick={() => setEditing({ type: "new-income" })}>
          <Plus size={16} /> Renda
        </Button>
      </div>
      {incomes.length === 0 ? (
        <p className="muted" style={{ margin: 0 }}>
          Nenhuma renda lançada neste mês. Ex.: “Salário” R$ 3.200 todo dia 5, ou “Freela” como variável.
        </p>
      ) : (
        <>
          <IncomeGroup title="Fixas" items={fixed} setEditing={setEditing} />
          <IncomeGroup title="Variáveis" items={variable} setEditing={setEditing} />
        </>
      )}
    </section>
  );
}

function BreakdownCard({ data, categories }: { data: MonthData; categories: Category[] }) {
  const s = data.summary;
  const total = Number(s.expense_total);
  if (total === 0) return null;
  const colors = new Map(categories.map((c) => [c.id, c.color ?? undefined]));
  const essentialPct = (Number(s.essential_total) / total) * 100;
  return (
    <section className="card stack">
      <h2>Para onde vai o dinheiro</h2>
      <div className="stack stack--tight">
        <div className="stacked-bar" aria-hidden>
          <div className="seg--needs" style={{ width: `${essentialPct}%` }} />
          <div className="seg--wants" style={{ width: `${100 - essentialPct}%` }} />
        </div>
        <div className="split small">
          <span>
            <i className="swatch" style={{ background: "#4e79a7" }} />
            Essencial <strong>{money(s.essential_total)}</strong>
          </span>
          <span>
            <i className="swatch swatch--expense" />
            Não essencial <strong>{money(s.non_essential_total)}</strong>
          </span>
        </div>
      </div>
      <ul className="breakdown">
        {s.by_category.map((c) => (
          <li key={c.category_id ?? "none"}>
            <div className="split">
              <span>
                <span className="dot" style={{ background: c.category_id ? colors.get(c.category_id) : undefined }} aria-hidden />
                {c.name}
              </span>
              <span className="num">
                {money(c.total)}{" "}
                <span className="muted small">{percent(Math.round((Number(c.total) / total) * 1000) / 10)}</span>
              </span>
            </div>
            {c.limit && c.limit_pct != null ? (
              <>
                <Bar
                  pct={Math.min(c.limit_pct, 100)}
                  color={c.limit_pct >= 100 ? "var(--error)" : c.limit_pct >= 80 ? "var(--warn)" : colors.get(c.category_id ?? "")}
                />
                <span className={`small ${c.limit_pct >= 100 ? "tone--error" : c.limit_pct >= 80 ? "tone--warn" : "muted"}`}>
                  {percent(c.limit_pct)} do limite de {money(c.limit)}
                </span>
              </>
            ) : (
              <Bar pct={(Number(c.total) / total) * 100} color={c.category_id ? colors.get(c.category_id) : undefined} />
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

function removeExpense(undo: ReturnType<typeof useUndo>, expense: Expense, scope: DeleteScope) {
  const what = scope === "following" ? `"${expense.description}" e as próximas excluídas` : `"${expense.description}" excluída`;
  undo.remove({ ids: [expense.id], message: what, commit: () => budgetApi.deleteExpense(expense.id, scope) });
}

function DeleteExpense({ expense, onDone }: { expense: Expense; onDone: () => void }) {
  const undo = useUndo();
  const repeats = expense.installment_group_id !== null || expense.recurring_id !== null;

  function del(scope: DeleteScope) {
    removeExpense(undo, expense, scope);
    onDone();
  }

  return (
    <div className="stack">
      <p style={{ margin: 0 }}>
        <strong>{expense.description}</strong> · {money(expense.amount)}
        {expense.installment_total && ` · parcela ${expense.installment_number}/${expense.installment_total}`}
      </p>
      {repeats && (
        <p className="muted" style={{ margin: 0 }}>
          {expense.installment_group_id ? "É uma compra parcelada." : "É uma conta fixa."} Excluir só esta ou também as próximas?
        </p>
      )}
      <div className="form-actions">
        <Button type="button" variant="secondary" onClick={onDone}>
          Cancelar
        </Button>
        {repeats && (
          <Button type="button" variant="danger" onClick={() => del("following")}>
            {expense.installment_group_id ? "Esta e as próximas parcelas" : "Deste mês em diante"}
          </Button>
        )}
        <Button type="button" variant="danger" onClick={() => del("one")}>
          <Trash2 size={16} /> {repeats ? "Só esta" : "Excluir"}
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- página

function MonthSkeleton() {
  return (
    <LoadingRegion label="Carregando o mês">
      <div className="stack" style={{ gap: 20 }}>
        <div className="kpis">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="kpi">
              <Skeleton width="50%" />
              <Skeleton height={28} width="70%" />
              <Skeleton height={12} width="40%" />
            </div>
          ))}
        </div>
        <div className="card stack">
          {[0, 1, 2, 3, 4].map((i) => (
            <Skeleton key={i} height={40} />
          ))}
        </div>
      </div>
    </LoadingRegion>
  );
}

/** Carrega o mês anterior e o próximo em segundo plano: trocar de mês fica instantâneo. */
function usePrefetchNeighbors(month: string) {
  const queryClient = useQueryClient();
  useEffect(() => {
    for (const m of [addMonths(month, -1), addMonths(month, 1)]) {
      void queryClient.prefetchQuery({ queryKey: keys.month(m), queryFn: () => budgetApi.month(m), staleTime: 30_000 });
    }
  }, [month, queryClient]);
}

export default function MonthPage() {
  const params = useParams();
  const month = params.month && /^\d{4}-\d{2}$/.test(params.month) ? params.month : thisMonth();
  const data = useMonth(month);
  usePrefetchNeighbors(month);
  const categories = useCategories();
  const [editing, setEditing] = useState<Editing>(null);
  const cats = categories.data ?? [];
  const close = () => setEditing(null);
  const isCurrent = month === thisMonth();

  const title = (
    <div className="month-nav">
      <Link className="icon-btn icon-btn--bordered" to={`/orcamento/${addMonths(month, -1)}`} aria-label="Mês anterior">
        <ChevronLeft size={18} />
      </Link>
      <h1>{monthLabel(month)}</h1>
      <Link className="icon-btn icon-btn--bordered" to={`/orcamento/${addMonths(month, 1)}`} aria-label="Próximo mês">
        <ChevronRight size={18} />
      </Link>
    </div>
  );

  return (
    <>
      <PageHeader
        title={title}
        subtitle={
          isCurrent ? (
            <span className="row" style={{ gap: 6 }}>
              <CalendarClock size={15} /> Mês atual
            </span>
          ) : (
            <Link to={`/orcamento/${thisMonth()}`}>Voltar para o mês atual</Link>
          )
        }
        actions={
          <span className="only-desktop">
            <span className="row">
              <Button type="button" variant="secondary" onClick={() => setEditing({ type: "new-income" })}>
                <Wallet size={16} /> Nova renda
              </Button>
              <Button type="button" onClick={() => setEditing({ type: "new-expense" })}>
                <Plus size={16} /> Nova conta
              </Button>
            </span>
          </span>
        }
      />

      {data.isPending && <MonthSkeleton />}
      {data.isError && <Alert tone="error">{errorMessage(data.error)}</Alert>}

      {data.data && (
        <div
          className={`stack ${data.isPlaceholderData ? "is-stale" : ""}`}
          style={{ gap: 20 }}
          aria-busy={data.isPlaceholderData || undefined}
        >
          {data.data.incomes.length === 0 && data.data.expenses.length === 0 ? (
            <div className="empty-hint">
              <span className="kpi__icon" aria-hidden>
                <Sparkles size={18} />
              </span>
              <div>
                <h2>Comece pela sua renda</h2>
                <p>
                  Lance quanto você recebe e depois as contas do mês. Ex.: “Salário” R$ 3.200 (fixa, todo mês, dia 5) e
                  “Aluguel” R$ 1.200 (se repete, vence dia 10). O que se repete aparece sozinho nos próximos meses; os
                  gastos futuros (aniversário, IPVA) vão no <Link to="/calendario">Calendário</Link>.
                </p>
                <div className="row" style={{ marginTop: 12 }}>
                  <Button type="button" onClick={() => setEditing({ type: "new-income" })}>
                    <Wallet size={16} /> Lançar renda
                  </Button>
                  <Link className="btn btn--secondary" to="/fixas">
                    <Repeat size={16} /> Contas fixas
                  </Link>
                </div>
              </div>
            </div>
          ) : (
            <>
              <Kpis data={data.data} />
              <ConsultantTeaser month={month} />
            </>
          )}
          <div className="layout-main-side">
            <ExpensesCard data={data.data} categories={cats} setEditing={setEditing} />
            <div className="stack" style={{ gap: 20 }}>
              <IncomesCard data={data.data} setEditing={setEditing} />
              <BreakdownCard data={data.data} categories={cats} />
            </div>
          </div>
        </div>
      )}

      {/* Fora do conteúdo (portal) para não andar junto nas animações de troca de página. */}
      {createPortal(
        <button type="button" className="fab no-print" aria-label="Adicionar conta ou renda" onClick={() => setEditing({ type: "choose" })}>
          <Plus size={26} />
        </button>,
        document.body,
      )}

      <Sheet open={editing?.type === "choose"} title="Adicionar" onClose={close}>
        <ul className="menu-list">
          <li>
            <button type="button" onClick={() => setEditing({ type: "new-expense" })}>
              <span className="kpi__icon kpi__icon--expense">
                <Receipt size={18} />
              </span>
              Nova conta
            </button>
          </li>
          <li>
            <button type="button" onClick={() => setEditing({ type: "new-income" })}>
              <span className="kpi__icon">
                <Wallet size={18} />
              </span>
              Nova renda
            </button>
          </li>
        </ul>
      </Sheet>

      <Sheet open={editing?.type === "new-expense"} title={`Nova conta · ${monthLabel(month)}`} onClose={close}>
        {editing?.type === "new-expense" && (
          <ExpenseForm month={month} categories={cats} draft={editing.draft} onDone={close} />
        )}
      </Sheet>
      <Sheet open={editing?.type === "expense"} title="Editar conta" onClose={close}>
        {editing?.type === "expense" && (
          <div className="stack">
            <ExpenseForm month={month} categories={cats} expense={editing.expense} onDone={close} />
            <div className="row only-mobile">
              <Button
                type="button"
                variant="secondary"
                onClick={() =>
                  setEditing({
                    type: "new-expense",
                    draft: {
                      description: editing.expense.description,
                      amount: editing.expense.amount,
                      category_id: editing.expense.category_id,
                      payment_method: editing.expense.payment_method,
                      notes: editing.expense.notes,
                    },
                  })
                }
              >
                <Copy size={16} /> Duplicar
              </Button>
              <Button type="button" variant="danger" onClick={() => setEditing({ type: "delete-expense", expense: editing.expense })}>
                <Trash2 size={16} /> Excluir conta
              </Button>
            </div>
          </div>
        )}
      </Sheet>
      <Sheet open={editing?.type === "delete-expense"} title="Excluir conta" onClose={close}>
        {editing?.type === "delete-expense" && <DeleteExpense expense={editing.expense} onDone={close} />}
      </Sheet>
      <Sheet open={editing?.type === "new-income"} title={`Nova renda · ${monthLabel(month)}`} onClose={close}>
        {editing?.type === "new-income" && <IncomeForm month={month} onDone={close} />}
      </Sheet>
      <Sheet open={editing?.type === "income"} title="Editar renda" onClose={close}>
        {editing?.type === "income" && <IncomeForm month={month} income={editing.income} onDone={close} />}
      </Sheet>
    </>
  );
}
