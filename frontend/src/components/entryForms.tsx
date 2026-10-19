import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Sparkles, Trash2 } from "lucide-react";

import {
  budgetApi,
  INTERVALS,
  keys,
  PAYMENT_METHODS,
  useBudgetMutation,
  type Category,
  type CategorySuggestion,
  type DeleteScope,
  type DescriptionSuggestion,
  type EditScope,
  type Expense,
  type ExpenseInput,
  type Income,
  type IncomeType,
  type Interval,
  type MonthData,
  type PaymentMethod,
} from "../api/budget";
import { extrasApi, useCards, type Card } from "../api/extras";
import { normalizeText } from "../lib/text";
import { errorMessage } from "../api/client";
import { announce } from "../lib/announce";
import { addMonths, money, moneyInput, monthLabel, parseMoney, shortDate, todayISO } from "../lib/format";
import { CategorySelect, MoneyInput, requireMoney } from "./budget";
import { Tip } from "./help";
import { Alert, Button } from "./ui";
import { useUndo } from "./undo";

/** Primeiro dia útil do mês do formulário, para sugerir datas dentro do mês aberto. */
function dateInMonth(month: string, day = new Date().getDate()): string {
  const [y, m] = month.split("-").map(Number);
  const last = new Date(y, m, 0).getDate();
  return `${month}-${String(Math.min(day, last)).padStart(2, "0")}`;
}

/** Vencimento da fatura em que cai uma compra (mesma regra do servidor). */
export function invoiceDue(card: Card, purchase: string): string {
  const [y, m, d] = purchase.split("-").map(Number);
  const clamp = (year: number, month: number, day: number) => Math.min(day, new Date(year, month, 0).getDate());
  let cy = y;
  let cm = m;
  if (d >= clamp(y, m, card.closing_day)) {
    cm += 1;
    if (cm > 12) {
      cm = 1;
      cy += 1;
    }
  }
  if (card.due_day <= card.closing_day) {
    cm += 1;
    if (cm > 12) {
      cm = 1;
      cy += 1;
    }
  }
  return `${cy}-${String(cm).padStart(2, "0")}-${String(clamp(cy, cm, card.due_day)).padStart(2, "0")}`;
}

/** Texto da regra sugerida: a primeira palavra "forte" da descrição (ex.: "uber" de "Uber *Trip"). */
function rulePattern(description: string): string {
  const words = normalizeText(description).split(/[^a-z0-9]+/).filter((w) => w.length >= 3);
  return words[0] ?? normalizeText(description);
}

// ---------------------------------------------------------------- sugestões

/** Sugestão de categoria e autocompletar enquanto a pessoa digita a descrição. */
function useDescriptionHelp(description: string, enabled: boolean) {
  const [category, setCategory] = useState<CategorySuggestion | null>(null);
  const [matches, setMatches] = useState<DescriptionSuggestion[]>([]);
  useEffect(() => {
    const text = description.trim();
    if (!enabled || text.length < 2) {
      setCategory(null);
      setMatches([]);
      return;
    }
    let alive = true;
    const timer = window.setTimeout(() => {
      budgetApi.suggestCategory(text).then((s) => alive && setCategory(s), () => undefined);
      budgetApi.suggestDescriptions(text).then((s) => alive && setMatches(s), () => undefined);
    }, 300);
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [description, enabled]);
  return { category, matches };
}

/** Campo de descrição com lista de sugestões (padrão "combobox" acessível). */
function DescriptionInput({
  value,
  onChange,
  matches,
  onPick,
  placeholder,
  labelledBy,
}: {
  value: string;
  onChange: (v: string) => void;
  matches: DescriptionSuggestion[];
  onPick: (s: DescriptionSuggestion) => void;
  placeholder: string;
  labelledBy: string;
}) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const listId = useId();
  const visible = open && matches.length > 0 && !(matches.length === 1 && matches[0].description === value);

  function pick(s: DescriptionSuggestion) {
    onPick(s);
    setOpen(false);
    setActive(-1);
    announce(`${s.description} selecionado; valor e categoria preenchidos`);
  }

  return (
    <div className="combo">
      <input
        role="combobox"
        aria-labelledby={labelledBy}
        aria-autocomplete="list"
        aria-expanded={visible}
        aria-controls={listId}
        aria-activedescendant={visible && active >= 0 ? `${listId}-${active}` : undefined}
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
          setActive(-1);
        }}
        onBlur={() => window.setTimeout(() => setOpen(false), 150)}
        onKeyDown={(e) => {
          if (!visible) return;
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setActive((a) => Math.min(a + 1, matches.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActive((a) => Math.max(a - 1, 0));
          } else if (e.key === "Enter" && active >= 0) {
            e.preventDefault();
            pick(matches[active]);
          } else if (e.key === "Escape") {
            setOpen(false);
          }
        }}
        placeholder={placeholder}
        required
        maxLength={120}
        autoFocus
        autoComplete="off"
      />
      {visible && (
        <ul className="combo__list" id={listId} role="listbox" aria-label="Lançamentos parecidos">
          {matches.map((s, i) => (
            <li
              key={s.description}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              className={i === active ? "is-active" : undefined}
              onMouseDown={(e) => {
                e.preventDefault();
                pick(s);
              }}
            >
              <span>{s.description}</span>
              <span className="muted small">
                {money(s.amount)} · {s.count}x
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ScopeChoice({ scope, setScope, what }: { scope: EditScope; setScope: (s: EditScope) => void; what: string }) {
  return (
    <fieldset className="radios">
      <legend className="field-label">Aplicar a alteração em</legend>
      <div className="segmented">
        <label>
          <input type="radio" name="scope" checked={scope === "one"} onChange={() => setScope("one")} />
          Só este mês
        </label>
        <label>
          <input type="radio" name="scope" checked={scope === "following"} onChange={() => setScope("following")} />
          {what}
        </label>
      </div>
    </fieldset>
  );
}

function SubmitRow({
  loading,
  onCancel,
  label,
  onAnother,
}: {
  loading: boolean;
  onCancel: () => void;
  label: string;
  onAnother?: () => void;
}) {
  return (
    <div className="form-actions">
      <Button type="button" variant="secondary" onClick={onCancel}>
        Cancelar
      </Button>
      {onAnother && (
        <Button type="button" variant="secondary" loading={loading} onClick={onAnother}>
          Salvar e adicionar outro
        </Button>
      )}
      <Button type="submit" loading={loading}>
        {label}
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------- conta (gasto)

type ExpenseKind = "single" | "installments" | "recurring";

export type ExpenseDraft = Partial<Pick<Expense, "description" | "amount" | "category_id" | "payment_method" | "notes" | "due_date">>;

export function ExpenseForm({
  month,
  categories,
  expense,
  draft,
  onDone,
}: {
  month: string;
  categories: Category[];
  /** Editando uma conta existente. */
  expense?: Expense;
  /** Nova conta já preenchida (ex.: "Duplicar"). */
  draft?: ExpenseDraft;
  onDone: () => void;
}) {
  const start = expense ?? draft;
  const [description, setDescription] = useState(start?.description ?? "");
  const [amount, setAmount] = useState(start?.amount ? moneyInput(start.amount) : "");
  const [categoryId, setCategoryId] = useState(start?.category_id ?? "");
  const [categoryTouched, setCategoryTouched] = useState(!!start?.category_id);
  const [dueDate, setDueDate] = useState(expense?.due_date ?? "");
  const [payment, setPayment] = useState<PaymentMethod | "">(start?.payment_method ?? "");
  const [notes, setNotes] = useState(start?.notes ?? "");
  const [kind, setKind] = useState<ExpenseKind>("single");
  const [installments, setInstallments] = useState("2");
  const [amountMode, setAmountMode] = useState<"parcel" | "total">("parcel");
  const [interval, setInterval] = useState<Interval>(1);
  const [until, setUntil] = useState("");
  const [scope, setScope] = useState<EditScope>("one");
  const [moreOpen, setMoreOpen] = useState(!!start?.notes);
  const [error, setError] = useState("");
  const [savedCount, setSavedCount] = useState(0);
  const [cardId, setCardId] = useState<string>(expense?.card_id ?? "");
  const [purchase, setPurchase] = useState(expense?.purchase_date ?? todayISO());
  const [duplicateOf, setDuplicateOf] = useState<string | null>(null);
  const [makeRule, setMakeRule] = useState(false);
  const [rulePatternText, setRulePatternText] = useState("");
  const cards = useCards();
  const queryClient = useQueryClient();
  const undo = useUndo();
  const descRef = useRef<HTMLDivElement>(null);
  const descLabel = useId();
  // "Já está paga": compras do dia a dia costumam ser lançadas depois de pagas.
  const [paidChoice, setPaidChoice] = useState<boolean | null>(null);
  const suggestedPaid = kind === "single" && (!dueDate || dueDate <= todayISO());
  const paid = kind === "recurring" ? false : (paidChoice ?? suggestedPaid);
  const repeats = !!expense && (expense.installment_group_id !== null || expense.recurring_id !== null);

  const help = useDescriptionHelp(description, !expense);
  const cardList = cards.data ?? [];
  const usesCard = !expense && kind !== "recurring" && payment === "credit" && cardList.length > 0;
  const card = usesCard ? cardList.find((c) => c.card.id === cardId)?.card ?? null : null;
  // Primeira vez escolhendo "Crédito": já sugere o (primeiro) cartão.
  useEffect(() => {
    if (usesCard && !cardId) setCardId(cardList[0].card.id);
  }, [usesCard, cardId, cardList]);
  // Oferece regra quando a pessoa escolhe uma categoria diferente da sugerida/original.
  const originalCategory = expense?.category_id ?? help.category?.category_id ?? "";
  const canOfferRule = categoryTouched && !!categoryId && categoryId !== originalCategory && description.trim().length >= 3;
  const suggestion = help.category && categories.some((c) => c.id === help.category!.category_id) ? help.category : null;
  // A sugestão preenche a categoria enquanto a pessoa não escolher outra.
  useEffect(() => {
    if (suggestion && !categoryTouched) setCategoryId(suggestion.category_id);
  }, [suggestion, categoryTouched]);

  const parsed = Number(parseMoney(amount) ?? 0);
  const count = Number(installments) || 0;
  const installmentHint =
    kind === "installments" && parsed > 0 && count >= 2
      ? amountMode === "total"
        ? `${count}x de ${money(parsed / count)}`
        : `Total da compra: ${money(parsed * count)}`
      : null;

  const save = useBudgetMutation(async () => {
    const value = requireMoney(amount);
    const category_id = categoryId || null;
    const extra = { payment_method: payment || null, notes: notes.trim() || null };
    if (makeRule && canOfferRule && rulePatternText.trim().length >= 2) {
      await extrasApi.createRule(rulePatternText.trim(), categoryId);
    }
    if (expense) {
      const before = {
        description: expense.description,
        amount: expense.amount,
        category_id: expense.category_id,
        due_date: expense.due_date,
        payment_method: expense.payment_method,
        notes: expense.notes,
      };
      await budgetApi.updateExpense(
        expense.id,
        { description, amount: value, category_id, due_date: dueDate || null, ...extra },
        scope,
      );
      undo.done({ message: "Conta alterada", revert: () => budgetApi.updateExpense(expense.id, before, scope) });
      return;
    }
    if (card) {
      await budgetApi.createExpense(month, {
        description,
        amount: value,
        category_id,
        ...extra,
        paid,
        card_id: card.id,
        purchase_date: purchase,
        installments: kind === "installments" ? count : null,
        amount_mode: amountMode,
      });
      return;
    }
    const data: ExpenseInput = { description, amount: value, category_id, due_date: dueDate || null, paid, ...extra };
    if (kind === "installments") {
      data.installments = count;
      data.amount_mode = amountMode;
    }
    if (kind === "recurring") {
      data.repeat = true;
      data.interval_months = interval;
      data.until_month = until || null;
    }
    // Parcelada ou que se repete: a 1ª data define o mês de início (ex.: começa no mês que vem).
    // Conta avulsa fica no mês aberto (a fatura de outubro pode vencer em novembro).
    const target = kind !== "single" && dueDate ? dueDate.slice(0, 7) : month;
    await budgetApi.createExpense(target, data);
  });

  function reset() {
    setDescription("");
    setAmount("");
    setCategoryId("");
    setCategoryTouched(false);
    setNotes("");
    setPaidChoice(null);
    setSavedCount((n) => n + 1);
    descRef.current?.querySelector("input")?.focus();
  }

  /** Já existe uma conta igual (nome e valor) neste mês? Avisa antes de salvar. */
  function findDuplicate(): string | null {
    if (expense || kind !== "single") return null;
    const data = queryClient.getQueryData<MonthData>(keys.month(month));
    const value = parseMoney(amount);
    const name = normalizeText(description);
    const twin = data?.expenses.find((e) => normalizeText(e.description) === name && Number(e.amount) === Number(value));
    return twin ? `${twin.description} · ${money(twin.amount)}${twin.due_date ? ` · ${shortDate(twin.due_date)}` : ""}` : null;
  }

  async function run(another: boolean) {
    setError("");
    if (duplicateOf === null) {
      const twin = findDuplicate();
      if (twin) {
        setDuplicateOf(twin);
        return;
      }
    }
    setDuplicateOf(null);
    try {
      await save.mutateAsync(undefined);
      announce(`${description} salva`);
      if (another) reset();
      else onDone();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void run(false);
  }

  return (
    <form className="inline-form entry-form" onSubmit={submit}>
      <Alert tone="error">{error}</Alert>
      {duplicateOf && (
        <Alert tone="info">
          Parece repetida: já existe “{duplicateOf}” neste mês. Toque em salvar de novo para lançar mesmo assim.
        </Alert>
      )}
      {savedCount > 0 && <Alert tone="success">{savedCount} conta(s) salva(s). Lance a próxima.</Alert>}

      <div className="field" ref={descRef}>
        <span className="field-label">
          <span id={descLabel}>Descrição</span>
          <Tip>Escreva como você reconhece a conta. Ex.: “Aluguel”, “Mercado Assaí”, “Uber”. A categoria é sugerida pelo nome.</Tip>
        </span>
        <DescriptionInput
          value={description}
          onChange={setDescription}
          matches={help.matches}
          labelledBy={descLabel}
          placeholder="Ex.: Mercado, Aluguel, Netflix"
          onPick={(s) => {
            setDescription(s.description);
            if (!amount) setAmount(moneyInput(s.amount));
            if (s.category_id) {
              setCategoryId(s.category_id);
              setCategoryTouched(true);
            }
            if (s.payment_method && !payment) setPayment(s.payment_method);
          }}
        />
      </div>

      {!expense && (
        <fieldset className="radios">
          <legend className="field-label">Como é essa conta?</legend>
          <div className="segmented segmented--3">
            <label>
              <input type="radio" name="kind" checked={kind === "single"} onChange={() => setKind("single")} />
              Uma vez
            </label>
            <label>
              <input type="radio" name="kind" checked={kind === "installments"} onChange={() => setKind("installments")} />
              Parcelada
            </label>
            <label>
              <input type="radio" name="kind" checked={kind === "recurring"} onChange={() => setKind("recurring")} />
              Se repete
            </label>
          </div>
        </fieldset>
      )}

      {kind === "installments" && (
        <div className="grid-2">
          <label>
            Número de parcelas
            <input type="number" inputMode="numeric" min={2} max={120} value={installments} onChange={(e) => setInstallments(e.target.value)} required />
          </label>
          <fieldset className="radios">
            <legend className="field-label">O valor digitado é</legend>
            <div className="segmented">
              <label>
                <input type="radio" name="mode" checked={amountMode === "parcel"} onChange={() => setAmountMode("parcel")} />
                De cada parcela
              </label>
              <label>
                <input type="radio" name="mode" checked={amountMode === "total"} onChange={() => setAmountMode("total")} />
                O total
              </label>
            </div>
          </fieldset>
        </div>
      )}

      <div className="grid-2">
        <label>
          <span className="field-label">
            {kind === "installments" ? (amountMode === "total" ? "Valor total da compra" : "Valor de cada parcela") : "Valor"}
          </span>
          <MoneyInput value={amount} onChange={setAmount} placeholder="Ex.: 150,00" />
          {installmentHint && <small className="muted">{installmentHint}</small>}
        </label>
        <label hidden={!!card}>
          <span className="field-label">
            {kind === "installments" ? "Vencimento da 1ª parcela" : kind === "recurring" ? "1º vencimento" : "Vencimento"}
            <Tip>
              {kind === "recurring"
                ? "O dia escolhido se repete nos próximos lançamentos. Ex.: 10/01 → vence todo dia 10."
                : "Opcional. Com data, a conta aparece no Calendário e você recebe aviso quando estiver perto de vencer."}
            </Tip>
          </span>
          <input type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} placeholder={dateInMonth(month)} />
        </label>
      </div>

      <fieldset className="radios">
        <legend className="field-label">Forma de pagamento</legend>
        <div className="chips">
          {PAYMENT_METHODS.map((p) => (
            <label key={p.value} className="chip-radio">
              <input type="radio" name="payment" checked={payment === p.value} onChange={() => setPayment(p.value)} />
              {p.label}
            </label>
          ))}
          {payment && (
            <button type="button" className="link-btn small" onClick={() => setPayment("")}>
              Limpar
            </button>
          )}
        </div>
      </fieldset>

      {usesCard && (
        <div className="grid-2 card-pick">
          <label>
            Cartão
            <select value={cardId} onChange={(e) => setCardId(e.target.value)}>
              {cardList.map((c) => (
                <option key={c.card.id} value={c.card.id}>
                  {c.card.name}
                </option>
              ))}
              <option value="">Sem cartão (lançar como conta comum)</option>
            </select>
          </label>
          {card && (
            <label>
              Data da compra
              <input type="date" value={purchase} onChange={(e) => setPurchase(e.target.value)} required />
              <small className="muted">
                Vai para a fatura de {monthLabel(invoiceDue(card, purchase).slice(0, 7))} (vence {shortDate(invoiceDue(card, purchase))})
              </small>
            </label>
          )}
        </div>
      )}

      {kind === "recurring" && (
        <div className="grid-2">
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
          <label>
            <span className="field-label">
              Até (opcional) <Tip>Último mês da conta. Deixe vazio se não tem fim (ex.: internet). Ex.: academia com plano até dezembro.</Tip>
            </span>
            <input type="month" value={until} min={dueDate ? dueDate.slice(0, 7) : month} onChange={(e) => setUntil(e.target.value)} />
          </label>
        </div>
      )}

      <label>
        <span className="field-label">
          Categoria
          {suggestion && !expense && (
            <span className={`suggest-chip ${categoryId === suggestion.category_id ? "is-applied" : ""}`}>
              <Sparkles size={12} aria-hidden /> Sugerido: {suggestion.name}
              <span className="sr-only">
                {suggestion.source === "history" ? " (pelo que você já lançou)" : " (pelo nome)"}
              </span>
            </span>
          )}
        </span>
        <CategorySelect
          categories={categories}
          value={categoryId}
          onChange={(v) => {
            setCategoryId(v);
            setCategoryTouched(true);
          }}
        />
      </label>

      {canOfferRule && (
        <div className="rule-offer">
          <label className="check">
            <input type="checkbox" checked={makeRule} onChange={(e) => {
              setMakeRule(e.target.checked);
              if (e.target.checked && !rulePatternText) setRulePatternText(rulePattern(description));
            }} />
            Sempre usar esta categoria quando a descrição tiver…
          </label>
          {makeRule && (
            <input
              aria-label="Texto da regra"
              value={rulePatternText}
              onChange={(e) => setRulePatternText(e.target.value)}
              maxLength={60}
              placeholder="Ex.: uber"
            />
          )}
        </div>
      )}

      <details className="more" open={moreOpen} onToggle={(e) => setMoreOpen((e.target as HTMLDetailsElement).open)}>
        <summary>Mais detalhes (observação)</summary>
        <div className="stack stack--tight" style={{ marginTop: 12 }}>
          <label>
            Observação
            <textarea value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={500} rows={2} placeholder="Ex.: dividido com a Ana; nota fiscal no e-mail" />
          </label>
        </div>
      </details>

      {repeats && (
        <ScopeChoice scope={scope} setScope={setScope} what={expense!.installment_group_id ? "Esta e as próximas parcelas" : "Este e os próximos meses"} />
      )}

      {!expense && kind !== "recurring" && (
        <label className="check">
          <input type="checkbox" checked={paid} onChange={(e) => setPaidChoice(e.target.checked)} />
          {kind === "installments" ? "A 1ª parcela já está paga" : "Já está paga"}
        </label>
      )}
      <SubmitRow
        loading={save.isPending}
        onCancel={onDone}
        label={duplicateOf ? "Salvar mesmo assim" : expense ? "Salvar" : "Adicionar conta"}
        onAnother={expense ? undefined : () => void run(true)}
      />
    </form>
  );
}

// ---------------------------------------------------------------- renda

export function IncomeForm({ month, income, onDone }: { month: string; income?: Income; onDone: () => void }) {
  const [description, setDescription] = useState(income?.description ?? "");
  const [amount, setAmount] = useState(income ? moneyInput(income.amount) : "");
  const [type, setType] = useState<IncomeType>(income?.income_type ?? "fixed");
  const [day, setDay] = useState(income?.day ? String(income.day) : "");
  const [notes, setNotes] = useState(income?.notes ?? "");
  const [repeat, setRepeat] = useState<"once" | "monthly" | "period">("once");
  const [until, setUntil] = useState(addMonths(month, 2));
  const [scope, setScope] = useState<EditScope>("one");
  const [error, setError] = useState("");
  const undo = useUndo();

  const save = useBudgetMutation(async () => {
    const value = requireMoney(amount);
    const data = {
      description,
      amount: value,
      income_type: type,
      day: day ? Number(day) : null,
      notes: notes.trim() || null,
    };
    if (income) await budgetApi.updateIncome(income.id, data, scope);
    else await budgetApi.createIncome(month, { ...data, repeat, until_month: repeat === "period" ? until : null });
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

  function del(deleteScope: DeleteScope) {
    const target = income!;
    undo.remove({
      ids: [target.id],
      message: `"${target.description}" excluída`,
      commit: () => budgetApi.deleteIncome(target.id, deleteScope),
    });
    onDone();
  }

  return (
    <form className="inline-form entry-form" onSubmit={submit}>
      <Alert tone="error">{error}</Alert>
      <label>
        Descrição
        <input
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder={type === "fixed" ? "Ex.: Salário, Aposentadoria" : "Ex.: Freela, Comissão, Uber"}
          required
          maxLength={120}
          autoFocus
        />
      </label>
      <fieldset className="radios">
        <legend className="field-label">
          Tipo de renda{" "}
          <Tip>
            Fixa: o mesmo valor todo mês (salário, aposentadoria). Variável: muda de mês para mês (bicos, comissões, vendas). Na
            previsão, a variável conta pela sua média.
          </Tip>
        </legend>
        <div className="segmented">
          <label>
            <input type="radio" name="type" checked={type === "fixed"} onChange={() => setType("fixed")} />
            Fixa
          </label>
          <label>
            <input type="radio" name="type" checked={type === "variable"} onChange={() => setType("variable")} />
            Variável
          </label>
        </div>
      </fieldset>
      <div className="grid-2">
        <label>
          {type === "variable" ? "Valor (deste mês)" : "Valor"}
          <MoneyInput value={amount} onChange={setAmount} placeholder="Ex.: 3.200,00" />
        </label>
        <label>
          <span className="field-label">
            Dia do recebimento <Tip>Opcional. Aparece no Calendário. Ex.: 5 para quem recebe no 5º dia.</Tip>
          </span>
          <input type="number" inputMode="numeric" min={1} max={31} value={day} onChange={(e) => setDay(e.target.value)} placeholder="Ex.: 5" />
        </label>
      </div>
      {!income && (
        <fieldset className="radios">
          <legend className="field-label">Repetir</legend>
          <div className="segmented segmented--3">
            <label>
              <input type="radio" name="repeat" checked={repeat === "once"} onChange={() => setRepeat("once")} />
              Só este mês
            </label>
            <label>
              <input type="radio" name="repeat" checked={repeat === "monthly"} onChange={() => setRepeat("monthly")} />
              Todo mês
            </label>
            <label>
              <input type="radio" name="repeat" checked={repeat === "period"} onChange={() => setRepeat("period")} />
              Por um período
            </label>
          </div>
        </fieldset>
      )}
      {!income && repeat === "period" && (
        <label className="narrow">
          Até o mês
          <input type="month" value={until} min={month} onChange={(e) => setUntil(e.target.value)} required />
        </label>
      )}
      <label>
        Observação
        <textarea value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={500} rows={2} placeholder="Ex.: 13º em dezembro; adiantamento dia 20" />
      </label>
      {income?.recurring_id && <ScopeChoice scope={scope} setScope={setScope} what="Este e os próximos meses" />}
      <SubmitRow loading={save.isPending} onCancel={onDone} label={income ? "Salvar" : "Adicionar renda"} />
      {income && (
        <div className="stack stack--tight" style={{ borderTop: "1px solid var(--border)", paddingTop: 16 }}>
          <Button type="button" variant="danger" onClick={() => del("one")}>
            <Trash2 size={16} /> {income.recurring_id ? "Excluir só deste mês" : "Excluir"}
          </Button>
          {income.recurring_id && (
            <Button type="button" variant="danger" onClick={() => del("following")}>
              Excluir deste mês em diante
            </Button>
          )}
        </div>
      )}
    </form>
  );
}
