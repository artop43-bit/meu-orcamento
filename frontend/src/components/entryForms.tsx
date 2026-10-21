import { useEffect, useId, useMemo, useRef, useState, type FormEvent } from "react";
import { createPortal } from "react-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CreditCard, Plus, Sparkles, Split, Trash2, Users } from "lucide-react";

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
  type ReceiptReading,
} from "../api/budget";
import { extrasApi, hasCredit, hasDebit, useCards, type Card } from "../api/extras";
import { CardForm } from "./CardForm";
import { ReceiptsField } from "./Receipts";
import { ReceiptReader } from "./ReceiptReader";
import { discard, isQueued, OFFLINE_SAVED, sendOrQueue } from "../lib/offline";
import { SplitForm } from "./SplitForm";
import { moneyApi, PROJECTS_KEY, useAccounts } from "../api/money";
import { DateField, DayField } from "./DateField";
import { normalizeText } from "../lib/text";
import { errorMessage } from "../api/client";
import { useMe } from "../api/auth";
import { announce } from "../lib/announce";
import { addMonths, money, moneyInput, monthLabel, parseMoney, shortDate, todayISO } from "../lib/format";
import { CategorySelect, MoneyInput, requireMoney } from "./budget";
import { Tip } from "./help";
import { Alert, Button, Sheet } from "./ui";
import { useUndo } from "./undo";

/** Vencimento da fatura em que cai uma compra (mesma regra do servidor). */
export function invoiceDue(card: Card, purchase: string): string {
  const [y, m, d] = purchase.split("-").map(Number);
  const clamp = (year: number, month: number, day: number) => Math.min(day, new Date(year, month, 0).getDate());
  let cy = y;
  let cm = m;
  const closing = card.closing_day ?? 1;
  const dueDay = card.due_day ?? 1;
  if (d >= clamp(y, m, closing)) {
    cm += 1;
    if (cm > 12) {
      cm = 1;
      cy += 1;
    }
  }
  if (dueDay <= closing) {
    cm += 1;
    if (cm > 12) {
      cm = 1;
      cy += 1;
    }
  }
  return `${cy}-${String(cm).padStart(2, "0")}-${String(clamp(cy, cm, dueDay)).padStart(2, "0")}`;
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
          Apenas este mês
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
  const [splitting, setSplitting] = useState(false);
  const [description, setDescription] = useState(start?.description ?? "");
  const [amount, setAmount] = useState(start?.amount ? moneyInput(start.amount) : "");
  const [categoryId, setCategoryId] = useState(start?.category_id ?? "");
  const [categoryTouched, setCategoryTouched] = useState(!!start?.category_id);
  const [dueDate, setDueDate] = useState(expense?.due_date ?? "");
  const [payment, setPayment] = useState<PaymentMethod | "">(start?.payment_method ?? "");
  const [notes, setNotes] = useState(start?.notes ?? "");
  const [kind, setKind] = useState<ExpenseKind>("single");
  const [installments, setInstallments] = useState("2");
  // Padrão: o valor digitado é o total da compra (é o número que a pessoa tem na mão).
  const [amountMode, setAmountMode] = useState<"parcel" | "total">("total");
  const [interval, setInterval] = useState<Interval>(1);
  const [until, setUntil] = useState("");
  const [scope, setScope] = useState<EditScope>("one");
  // v1.4: projeto/etiqueta (opcional).
  const projects = useQuery({ queryKey: PROJECTS_KEY, queryFn: moneyApi.projects });
  const [project, setProject] = useState("");
  const projectLoaded = useRef(false);
  useEffect(() => {
    if (projectLoaded.current || !expense?.project_id || !projects.data) return;
    projectLoaded.current = true;
    setProject(projects.data.find((p) => p.id === expense.project_id)?.name ?? "");
  }, [expense?.project_id, projects.data]);
  const [moreOpen, setMoreOpen] = useState(!!start?.notes || !!expense?.project_id);
  const [error, setError] = useState("");
  const [savedCount, setSavedCount] = useState(0);
  const [cardId, setCardId] = useState<string>(expense?.card_id ?? "");
  const [debitCardId, setDebitCardId] = useState<string>(expense?.debit_card_id ?? "");
  const [pendingReceipts, setPendingReceipts] = useState<File[]>([]);
  const createdRef = useRef<Expense[] | null>(null);
  // Sem internet: o lançamento ficou na fila do aparelho (id para poder desfazer).
  const queuedRef = useRef<string | null>(null);
  // v1.3: compra dividida em categorias, cada parte com o seu valor.
  const [parts, setParts] = useState<{ categoryId: string; amount: string }[] | null>(null);
  const [readInfo, setReadInfo] = useState("");
  const [purchase, setPurchase] = useState(expense?.purchase_date ?? todayISO());
  const [duplicateOf, setDuplicateOf] = useState<string | null>(null);
  const [makeRule, setMakeRule] = useState(false);
  const [rulePatternText, setRulePatternText] = useState("");
  const [accountId, setAccountId] = useState(expense?.account_id ?? "");
  const accounts = useAccounts();
  const accountList = (accounts.data ?? []).map((b) => b.account);
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
  const allCards = useMemo(() => (cards.data ?? []).map((s) => s.card), [cards.data]);
  const creditCards = allCards.filter(hasCredit);
  const debitCards = allCards.filter(hasDebit);
  // Crédito: a compra é sempre de um cartão (sem opção vazia). Débito: idem, exceto parcelada.
  const wantsCredit = !expense && kind !== "recurring" && payment === "credit";
  const wantsDebit = !expense && kind !== "installments" && payment === "debit";
  const usesCard = wantsCredit && creditCards.length > 0;
  const usesDebit = wantsDebit && debitCards.length > 0;
  const card = usesCard ? creditCards.find((c) => c.id === cardId) ?? creditCards[0] ?? null : null;
  const debitCard = usesDebit ? debitCards.find((c) => c.id === debitCardId) ?? debitCards[0] ?? null : null;
  const missingCard = (wantsCredit && creditCards.length === 0) || (wantsDebit && debitCards.length === 0);
  const [addingCard, setAddingCard] = useState(false);
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
  // Divisão em categorias: só para compra única (sem parcelas nem repetição).
  const canSplitCategories = !expense && kind === "single";
  const activeParts = canSplitCategories ? parts : null;
  const partsRest = activeParts ? parsed - activeParts.reduce((sum, p) => sum + Number(parseMoney(p.amount) ?? 0), 0) : 0;

  function setPart(index: number, change: Partial<{ categoryId: string; amount: string }>) {
    setParts((list) => list && list.map((p, i) => (i === index ? { ...p, ...change } : p)));
  }

  /** Cria a despesa; sem internet, guarda na fila do aparelho. */
  async function create(target: string, data: ExpenseInput): Promise<Expense[] | null> {
    const body = activeParts
      ? { ...data, category_id: activeParts[0]!.categoryId, parts: activeParts.map((p) => ({ category_id: p.categoryId, amount: requireMoney(p.amount) })) }
      : data;
    const result = await sendOrQueue(
      { kind: "expense", method: "POST", path: `/months/${target}/expenses`, body, label: data.description },
      (client_ref) => budgetApi.createExpense(target, { ...body, client_ref }),
    );
    if (isQueued(result)) {
      queuedRef.current = result.queued;
      return null;
    }
    return result;
  }

  /** Foto lida: preenche o que foi encontrado; a pessoa confere antes de salvar. */
  function applyReading(reading: ReceiptReading, file: File) {
    if (reading.description && !description.trim()) setDescription(reading.description);
    if (reading.amount) setAmount(moneyInput(reading.amount));
    if (reading.date) {
      if (usesCard) setPurchase(reading.date);
      else setDueDate(reading.date);
      // Boleto: a data é o vencimento (ainda a pagar). Cupom: a compra já foi paga.
      if (reading.kind === "boleto") setPaidChoice(false);
    }
    if (reading.kind === "boleto" && !payment) setPayment("boleto");
    setPendingReceipts((list) => [...list, file].slice(0, 3));
    setReadInfo(
      reading.amount || reading.date
        ? "Lido do comprovante: confira o valor, a data e a descrição antes de salvar. A foto fica anexada."
        : "Não encontramos o valor nem a data na foto. Preencha à mão; a foto fica anexada.",
    );
  }
  const startMonth = (card ? invoiceDue(card, purchase) : dueDate || `${month}-01`).slice(0, 7);
  const installmentSummary =
    kind === "installments" && parsed > 0 && count >= 2
      ? {
          parcel: amountMode === "total" ? parsed / count : parsed,
          total: amountMode === "total" ? parsed : parsed * count,
          last: monthLabel(addMonths(startMonth, count - 1), true),
        }
      : null;

  const save = useBudgetMutation(async () => {
    const value = requireMoney(amount);
    const category_id = categoryId || null;
    const extra = {
      payment_method: payment || null,
      notes: notes.trim() || null,
      // Na edição, só manda o projeto depois de carregado (senão apagaria o atual).
      project_name: expense?.project_id && !projectLoaded.current ? undefined : project.trim(),
      account_id: card || debitCard ? null : accountId || null,
    };
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
        account_id: expense.account_id,
      };
      await budgetApi.updateExpense(
        expense.id,
        { description, amount: value, category_id, due_date: dueDate || null, ...extra },
        scope,
      );
      undo.done({ message: "Despesa alterada", revert: () => budgetApi.updateExpense(expense.id, before, scope) });
      return;
    }
    if (card) {
      createdRef.current = await create(month, {
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
    if (debitCard) {
      // Débito: entra paga na data da compra e sai da conta vinculada ao cartão.
      const data: ExpenseInput = {
        description,
        amount: value,
        category_id,
        ...extra,
        paid: true,
        debit_card_id: debitCard.id,
        purchase_date: dueDate || todayISO(),
        due_date: dueDate || todayISO(),
      };
      if (kind === "recurring") {
        data.repeat = true;
        data.interval_months = interval;
        data.until_month = until || null;
      }
      createdRef.current = await create(kind === "recurring" && dueDate ? dueDate.slice(0, 7) : month, data);
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
    createdRef.current = await create(target, data);
  });

  function reset() {
    setDescription("");
    setAmount("");
    setCategoryId("");
    setCategoryTouched(false);
    setNotes("");
    setPaidChoice(null);
    setParts(null);
    setReadInfo("");
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
    if (activeParts) {
      if (activeParts.some((p) => !p.categoryId || !parseMoney(p.amount))) {
        setError("Escolha a categoria e o valor de cada parte.");
        return;
      }
      if (Math.abs(partsRest) >= 0.005) {
        setError(`A soma das partes precisa ser igual ao total. ${partsRest > 0 ? "Falta distribuir" : "As partes passam do total em"} ${money(Math.abs(partsRest))}.`);
        return;
      }
    }
    try {
      createdRef.current = null;
      queuedRef.current = null;
      await save.mutateAsync(undefined);
      const queued = queuedRef.current;
      if (queued) {
        // Sem internet: fica na fila e sobe sozinho depois (comprovantes precisam de conexão).
        undo.done({
          message: pendingReceipts.length ? `${OFFLINE_SAVED} Anexe o comprovante depois, com internet.` : OFFLINE_SAVED,
          revert: async () => discard(queued),
        });
        if (another) reset();
        else onDone();
        return;
      }
      // Comprovantes escolhidos antes de salvar vão para a despesa criada (a 1ª parcela).
      const first = (createdRef.current as Expense[] | null)?.[0];
      if (first && pendingReceipts.length) {
        await budgetApi.addReceipts(first.id, pendingReceipts);
        setPendingReceipts([]);
        await queryClient.invalidateQueries({ queryKey: ["budget"] });
      }
      announce(`Despesa “${description}” salva`);
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

  const dateLabel = debitCard
    ? kind === "recurring"
      ? "Primeira compra"
      : "Data da compra"
    : kind === "installments"
      ? "Vencimento da 1ª parcela"
      : kind === "recurring"
        ? "Primeiro vencimento"
        : "Vencimento (opcional)";

  return (
    <form className="inline-form entry-form" onSubmit={submit}>
      <Alert tone="error">{error}</Alert>
      {duplicateOf && (
        <Alert tone="info">
          Possível duplicidade: já existe “{duplicateOf}” neste mês. Salve novamente para confirmar o lançamento.
        </Alert>
      )}
      {savedCount > 0 && <Alert tone="success">{savedCount} despesa(s) salva(s). Preencha a próxima.</Alert>}
      {!expense && <ReceiptReader onRead={applyReading} />}
      {readInfo && <Alert tone="info">{readInfo}</Alert>}

      <div className="field" ref={descRef}>
        <span className="field-label">
          <span id={descLabel}>Descrição</span>
          <Tip>Nome da despesa, como aparece para você ou no extrato. A categoria é sugerida automaticamente.</Tip>
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
          <legend className="field-label">Tipo de despesa</legend>
          <div className="segmented segmented--3">
            <label>
              <input type="radio" name="kind" checked={kind === "single"} onChange={() => setKind("single")} />
              Única
            </label>
            <label>
              <input type="radio" name="kind" checked={kind === "installments"} onChange={() => setKind("installments")} />
              Parcelada
            </label>
            <label>
              <input type="radio" name="kind" checked={kind === "recurring"} onChange={() => setKind("recurring")} />
              Recorrente
            </label>
          </div>
        </fieldset>
      )}

      {/* Passo 1: valor — na parcelada, a escolha total × parcela fica junto do campo. */}
      <fieldset className="radios amount-block">
        <legend className="field-label">Valor</legend>
        {kind === "installments" && (
          <div className="segmented segmented--compact" role="radiogroup" aria-label="O valor informado é">
            <label>
              <input type="radio" name="mode" checked={amountMode === "total"} onChange={() => setAmountMode("total")} />
              Total da compra
            </label>
            <label>
              <input type="radio" name="mode" checked={amountMode === "parcel"} onChange={() => setAmountMode("parcel")} />
              Valor da parcela
            </label>
          </div>
        )}
        <MoneyInput
          value={amount}
          onChange={setAmount}
          placeholder="0,00"
          label={kind === "installments" ? (amountMode === "total" ? "Valor total da compra" : "Valor de cada parcela") : "Valor"}
        />
      </fieldset>

      {/* Passo 2: parcelas, com atalhos e resumo ao vivo. */}
      {kind === "installments" && (
        <div className="stack stack--tight">
          <label className="narrow">
            Número de parcelas
            <input type="number" inputMode="numeric" min={2} max={120} value={installments} onChange={(e) => setInstallments(e.target.value)} required />
          </label>
          <div className="chips" role="group" aria-label="Atalhos de parcelas">
            {[2, 3, 6, 10, 12].map((n) => (
              <button
                key={n}
                type="button"
                className={`chip-btn ${count === n ? "is-active" : ""}`}
                aria-pressed={count === n}
                onClick={() => setInstallments(String(n))}
              >
                {n}x
              </button>
            ))}
          </div>
          {installmentSummary && (
            <p className="summary-box" aria-live="polite">
              <strong>
                {count}x de {money(installmentSummary.parcel)}
              </strong>{" "}
              · total {money(installmentSummary.total)} · última parcela em {installmentSummary.last}
            </p>
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
              Até (opcional) <Tip>Último mês da recorrência. Deixe em branco para manter sem data de término.</Tip>
            </span>
            <DateField month value={until} min={dueDate ? dueDate.slice(0, 7) : month} onChange={setUntil} />
          </label>
        </div>
      )}

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

      {missingCard && (
        <div className="card-missing">
          <p className="muted small">
            {payment === "credit" ? "Nenhum cartão de crédito cadastrado." : "Nenhum cartão de débito cadastrado."} Cadastre o cartão para
            {payment === "credit" ? " alocar a compra na fatura certa." : " descontar a compra da conta certa."}
          </p>
          <Button type="button" variant="secondary" onClick={() => setAddingCard(true)}>
            <CreditCard size={16} /> Cadastrar cartão
          </Button>
        </div>
      )}

      {usesDebit && (
        <div className="grid-2 card-pick">
          <label>
            Cartão de débito
            <select value={debitCard?.id ?? ""} onChange={(e) => setDebitCardId(e.target.value)} required>
              {debitCards.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          <p className="muted small card-pick__note">Entra como paga e sai da conta vinculada ao cartão. Não usa limite nem fatura.</p>
        </div>
      )}

      {usesCard && (
        <div className="grid-2 card-pick">
          <label>
            Cartão de crédito
            <select value={card?.id ?? ""} onChange={(e) => setCardId(e.target.value)} required>
              {creditCards.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          {card && (
            <label>
              Data da compra
              <DateField value={purchase} onChange={setPurchase} required />
              <small className="muted">
                Fatura de {monthLabel(invoiceDue(card, purchase).slice(0, 7))}, vencimento em {shortDate(invoiceDue(card, purchase))}
              </small>
            </label>
          )}
        </div>
      )}

      {!card && (
        <div className="grid-2">
          <label>
            <span className="field-label">
              {dateLabel}
              <Tip>
                {kind === "recurring"
                  ? "O dia informado se repete nos lançamentos seguintes."
                  : "Com vencimento, a despesa aparece no Calendário e nos lembretes."}
              </Tip>
            </span>
            <DateField value={dueDate} onChange={setDueDate} />
          </label>
          {accountList.length > 0 && !debitCard && (
            <label>
              Conta de pagamento
              <select value={accountId} onChange={(e) => setAccountId(e.target.value)}>
                <option value="">Não informar</option>
                {accountList.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
      )}

      {activeParts ? (
        <fieldset className="split-parts">
          <legend className="field-label">Categorias e valores</legend>
          {activeParts.map((part, index) => (
            <div className="split-parts__row" key={index}>
              <CategorySelect
                categories={categories}
                value={part.categoryId}
                onChange={(v) => setPart(index, { categoryId: v })}
                label={`Categoria da parte ${index + 1}`}
              />
              <MoneyInput value={part.amount} onChange={(v) => setPart(index, { amount: v })} label={`Valor da parte ${index + 1}`} />
              <button
                type="button"
                className="icon-btn"
                aria-label={`Remover a parte ${index + 1}`}
                disabled={activeParts.length <= 2}
                onClick={() => setParts((list) => list && list.filter((_, i) => i !== index))}
              >
                <Trash2 size={16} aria-hidden />
              </button>
            </div>
          ))}
          <p className={`summary-box small ${Math.abs(partsRest) < 0.005 ? "" : "tone--warn"}`} aria-live="polite">
            {Math.abs(partsRest) < 0.005
              ? `As partes somam o total de ${money(parsed)}.`
              : partsRest > 0
                ? `Falta distribuir ${money(partsRest)} do total de ${money(parsed)}.`
                : `As partes passam do total em ${money(-partsRest)}.`}
          </p>
          <div className="row" style={{ gap: 12, flexWrap: "wrap" }}>
            {activeParts.length < 6 && (
              <button
                type="button"
                className="link-btn small"
                onClick={() => setParts((list) => list && [...list, { categoryId: "", amount: partsRest > 0 ? moneyInput(partsRest.toFixed(2)) : "" }])}
              >
                <Plus size={14} aria-hidden /> Adicionar categoria
              </button>
            )}
            <button
              type="button"
              className="link-btn small"
              onClick={() => {
                setCategoryId(activeParts[0]!.categoryId);
                setParts(null);
              }}
            >
              Não dividir
            </button>
          </div>
        </fieldset>
      ) : (
      <label>
        <span className="field-label">
          Categoria
          {suggestion && !expense && (
            <span className={`suggest-chip ${categoryId === suggestion.category_id ? "is-applied" : ""}`}>
              <Sparkles size={12} aria-hidden /> Sugestão: {suggestion.name}
              <span className="sr-only">
                {suggestion.source === "rule" ? " (regra)" : suggestion.source === "history" ? " (histórico)" : " (descrição)"}
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
      )}
      {!activeParts && canSplitCategories && (
        <button
          type="button"
          className="link-btn small split-parts__start"
          onClick={() => setParts([{ categoryId, amount }, { categoryId: "", amount: "" }])}
        >
          <Split size={14} aria-hidden /> Dividir em categorias
        </button>
      )}

      {canOfferRule && (
        <div className="rule-offer">
          <label className="check">
            <input
              type="checkbox"
              checked={makeRule}
              onChange={(e) => {
                setMakeRule(e.target.checked);
                if (e.target.checked && !rulePatternText) setRulePatternText(rulePattern(description));
              }}
            />
            Criar regra: usar esta categoria sempre que a descrição contiver
          </label>
          {makeRule && (
            <input aria-label="Texto da regra" value={rulePatternText} onChange={(e) => setRulePatternText(e.target.value)} maxLength={60} placeholder="Ex.: uber" />
          )}
        </div>
      )}

      <ReceiptsField
        expenseId={expense?.id}
        saved={expense?.receipt_ids ?? []}
        pending={pendingReceipts}
        setPending={setPendingReceipts}
      />

      {expense && (
        <div className="split-entry">
          <Button type="button" variant="secondary" onClick={() => setSplitting(true)}>
            <Users size={16} /> Dividir com outras pessoas
          </Button>
        </div>
      )}

      <details className="more" open={moreOpen} onToggle={(e) => setMoreOpen((e.target as HTMLDetailsElement).open)}>
        <summary>Observação e projeto</summary>
        <div className="stack stack--tight" style={{ marginTop: 12 }}>
          <label>
            <span className="sr-only">Observação</span>
            <textarea value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={500} rows={2} placeholder="Informações adicionais" />
          </label>
          <label>
            <span className="field-label">
              Projeto (opcional) <Tip>Junta despesas de categorias diferentes, como “Viagem Bahia” ou “Reforma”. O total aparece na Busca.</Tip>
            </span>
            <input value={project} onChange={(e) => setProject(e.target.value)} maxLength={40} list="projetos" placeholder="Ex.: Viagem Bahia" autoComplete="off" />
            <datalist id="projetos">
              {(projects.data ?? []).map((p) => (
                <option key={p.id} value={p.name} />
              ))}
            </datalist>
          </label>
        </div>
      </details>

      {repeats && (
        <ScopeChoice scope={scope} setScope={setScope} what={expense!.installment_group_id ? "Esta e as próximas parcelas" : "Este mês e os seguintes"} />
      )}

      {!expense && kind !== "recurring" && !debitCard && (
        <label className="check">
          <input type="checkbox" checked={paid} onChange={(e) => setPaidChoice(e.target.checked)} />
          {kind === "installments" ? "Primeira parcela já paga" : "Já paga"}
        </label>
      )}
      <SubmitRow
        loading={save.isPending}
        onCancel={onDone}
        label={duplicateOf ? "Salvar mesmo assim" : expense ? "Salvar" : "Adicionar despesa"}
        onAnother={expense ? undefined : () => void run(true)}
      />
      {/* Fora do <form> da despesa (portal): um formulário dentro de outro enviaria os dois. */}
      {expense &&
        createPortal(
          <Sheet open={splitting} title="Dividir despesa" onClose={() => setSplitting(false)}>
            {splitting && <SplitForm expense={expense} onDone={() => setSplitting(false)} />}
          </Sheet>,
          document.body,
        )}
      {createPortal(
        <Sheet open={addingCard} title="Novo cartão" onClose={() => setAddingCard(false)}>
          {addingCard && (
            <CardForm
              defaultKind={payment === "debit" ? "debit" : "credit"}
              onDone={(created) => {
                setAddingCard(false);
                if (created && payment === "debit") setDebitCardId(created.id);
                if (created && payment === "credit") setCardId(created.id);
              }}
            />
          )}
        </Sheet>,
        document.body,
      )}
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
  const [accountId, setAccountId] = useState(income?.account_id ?? "");
  // v1.4: só aparece para quem ligou "Sou MEI" em Preferências.
  const me = useMe();
  const [mei, setMei] = useState(income?.mei ?? false);
  const accounts = useAccounts();
  const accountList = (accounts.data ?? []).map((b) => b.account);
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
      account_id: accountId || null,
      ...(me.data?.mei ? { mei } : {}),
    };
    if (income) {
      await budgetApi.updateIncome(income.id, data, scope);
      return null;
    }
    const body = { ...data, repeat, until_month: repeat === "period" ? until : null };
    const result = await sendOrQueue(
      { kind: "income", method: "POST", path: `/months/${month}/incomes`, body, label: `${description} (receita)` },
      (client_ref) => budgetApi.createIncome(month, { ...body, client_ref }),
    );
    return isQueued(result) ? result.queued : null;
  });

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const queued = await save.mutateAsync(undefined);
      if (queued) undo.done({ message: OFFLINE_SAVED, revert: async () => discard(queued) });
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
          placeholder={type === "fixed" ? "Ex.: Salário, Aposentadoria" : "Ex.: Freelance, Comissão"}
          required
          maxLength={120}
          autoFocus
        />
      </label>
      <fieldset className="radios">
        <legend className="field-label">
          Tipo de receita{" "}
          <Tip>Fixa: mesmo valor todo mês. Variável: valor muda a cada mês; na projeção, conta pela média.</Tip>
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
          {type === "variable" ? "Valor no mês" : "Valor"}
          <MoneyInput value={amount} onChange={setAmount} placeholder="0,00" />
        </label>
        <label>
          <span className="field-label">
            Dia do recebimento <Tip>Opcional. Exibe a receita no dia correspondente do Calendário.</Tip>
          </span>
          <DayField
            value={day}
            onChange={setDay}
            month={income?.month?.slice(0, 7) ?? month}
            recurring={income ? Boolean(income.recurring_id) : repeat !== "once"}
          />
        </label>
      </div>
      {!income && (
        <fieldset className="radios">
          <legend className="field-label">Recorrência</legend>
          <div className="segmented segmented--3">
            <label>
              <input type="radio" name="repeat" checked={repeat === "once"} onChange={() => setRepeat("once")} />
              Apenas este mês
            </label>
            <label>
              <input type="radio" name="repeat" checked={repeat === "monthly"} onChange={() => setRepeat("monthly")} />
              Todo mês
            </label>
            <label>
              <input type="radio" name="repeat" checked={repeat === "period"} onChange={() => setRepeat("period")} />
              Por período
            </label>
          </div>
        </fieldset>
      )}
      {!income && repeat === "period" && (
        <label className="narrow">
          Até
          <DateField month value={until} min={month} onChange={setUntil} required />
        </label>
      )}
      {accountList.length > 0 && (
        <label>
          Conta de recebimento
          <select value={accountId} onChange={(e) => setAccountId(e.target.value)}>
            <option value="">Não informar</option>
            {accountList.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        </label>
      )}
      {me.data?.mei && (
        <label className="check">
          <input type="checkbox" checked={mei} onChange={(e) => setMei(e.target.checked)} />
          Faturamento do MEI (conta para o teto anual)
        </label>
      )}
      <label>
        Observação
        <textarea value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={500} rows={2} placeholder="Informações adicionais" />
      </label>
      {income?.recurring_id && <ScopeChoice scope={scope} setScope={setScope} what="Este mês e os seguintes" />}
      <SubmitRow loading={save.isPending} onCancel={onDone} label={income ? "Salvar" : "Adicionar receita"} />
      {income && (
        <div className="stack stack--tight" style={{ borderTop: "1px solid var(--border)", paddingTop: 16 }}>
          <Button type="button" variant="danger" onClick={() => del("one")}>
            <Trash2 size={16} /> {income.recurring_id ? "Excluir apenas este mês" : "Excluir"}
          </Button>
          {income.recurring_id && (
            <Button type="button" variant="danger" onClick={() => del("following")}>
              Excluir este mês e os seguintes
            </Button>
          )}
        </div>
      )}
    </form>
  );
}
