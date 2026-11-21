import { useEffect, useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { errorMessage } from "../../api/client";
import {
  messagingApi,
  messagingKeys,
  useBudgetContext,
  type MessagingChat,
  type MessagingMessage,
} from "../../api/messaging";
import { parseMoney } from "../../lib/format";
import { extractMoneyFromMessage } from "../../lib/messaging";
import { Sheet } from "../ui";

function newClientRef(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  const hex = () => Math.floor((1 + Math.random()) * 0x10000).toString(16).slice(1);
  return `${hex()}${hex()}-${hex()}-4${hex().slice(1)}-8${hex().slice(1)}-${hex()}${hex()}${hex()}`;
}

export interface BudgetEntrySubmitState {
  description: string;
  amount: string;
  kind: "income" | "expense";
  paymentMethod: string;
  cardId: string;
  isPending: boolean;
  isSuccess: boolean;
}

/** Verifica se o botão "Salvar no Meu Orçamento" pode enviar (impede reenvio enquanto salva ou já salvo). */
export function canSubmitBudgetEntry(state: BudgetEntrySubmitState): boolean {
  const parsed = parseMoney(state.amount);
  if (!state.description.trim() || !parsed || Number(parsed) <= 0) return false;
  if (state.isPending || state.isSuccess) return false;
  if (state.kind === "expense" && state.paymentMethod === "credit" && !state.cardId) return false;
  return true;
}

/** Folha modal para lançar uma receita ou despesa no Meu Orçamento direto da conversa. */
export function BudgetEntrySheet({
  chat,
  trigger,
  open,
  onClose,
}: {
  chat: MessagingChat;
  trigger: { seq: number; message?: MessagingMessage } | null;
  open: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [entryKind, setEntryKind] = useState<"income" | "expense">("expense");
  const [entryDesc, setEntryDesc] = useState("");
  const [entryAmount, setEntryAmount] = useState("");
  const [entryCategoryId, setEntryCategoryId] = useState("");
  const [entryCardId, setEntryCardId] = useState("");
  const [entryPayment, setEntryPayment] = useState("pix");
  const [entryPaid, setEntryPaid] = useState(true);
  const [entryClientRef, setEntryClientRef] = useState(() => newClientRef());
  const [entryNotice, setEntryNotice] = useState<string | null>(null);

  const budgetCtx = useBudgetContext(chat.id, open).data;

  const budgetMutation = useMutation({
    mutationFn: () =>
      messagingApi.createBudgetEntry(chat.id, {
        kind: entryKind,
        description: entryDesc.trim(),
        amount: parseMoney(entryAmount) ?? "",
        category_id: entryKind === "expense" && entryCategoryId ? entryCategoryId : null,
        payment_method: entryKind === "expense" ? entryPayment : null,
        card_id: entryKind === "expense" && entryPayment === "credit" ? entryCardId || null : null,
        paid: entryPayment === "credit" ? false : entryPaid,
        client_ref: entryClientRef,
      }),
    onSuccess: (res) => {
      void qc.invalidateQueries({ queryKey: messagingKeys.budgetContext(chat.id) });
      void qc.invalidateQueries({ queryKey: messagingKeys.budgetContext(null) });
      setEntryNotice(
        `${res.kind === "income" ? "Receita" : "Despesa"} "${res.description}" registrada no Meu Orçamento (${res.month}).`,
      );
      window.setTimeout(() => {
        onClose();
        setEntryNotice(null);
      }, 1100);
    },
  });

  useEffect(() => {
    if (!trigger) return;
    const extracted = extractMoneyFromMessage(trigger.message?.body ?? "", chat.name);
    setEntryKind(extracted.kind);
    setEntryDesc(extracted.description);
    setEntryAmount(extracted.amount);
    setEntryPayment(extracted.paymentMethod);
    setEntryPaid(extracted.paymentMethod !== "credit");
    setEntryCardId("");
    setEntryCategoryId("");
    setEntryClientRef(newClientRef());
    setEntryNotice(null);
    budgetMutation.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trigger?.seq, chat.name]);

  const canSubmit = canSubmitBudgetEntry({
    description: entryDesc,
    amount: entryAmount,
    kind: entryKind,
    paymentMethod: entryPayment,
    cardId: entryCardId,
    isPending: budgetMutation.isPending,
    isSuccess: budgetMutation.isSuccess,
  });

  function submitBudgetEntry(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    budgetMutation.mutate();
  }

  return (
    <Sheet open={open} title="Lançar no Meu Orçamento" onClose={onClose}>
      <form className="stack" onSubmit={submitBudgetEntry}>
        <p className="muted small m-0">
          Registra o lançamento diretamente no mês atual do <strong>Meu Orçamento</strong> vinculado a{" "}
          <strong>{chat.name}</strong>.
        </p>

        <div className="wa-filters wa-filters--flush" role="group" aria-label="Tipo de lançamento">
          <button
            type="button"
            className="filter-chip"
            aria-pressed={entryKind === "expense"}
            onClick={() => setEntryKind("expense")}
          >
            Despesa
          </button>
          <button
            type="button"
            className="filter-chip"
            aria-pressed={entryKind === "income"}
            onClick={() => setEntryKind("income")}
          >
            Receita
          </button>
        </div>

        <div className="field">
          <label htmlFor="wa-budget-desc">Descrição</label>
          <input
            id="wa-budget-desc"
            type="text"
            className="input"
            required
            maxLength={120}
            value={entryDesc}
            onChange={(e) => setEntryDesc(e.target.value)}
            placeholder="Ex.: Consultoria, Almoço, Pix recebido..."
          />
        </div>

        <div className="field">
          <label htmlFor="wa-budget-amount">Valor (R$)</label>
          <input
            id="wa-budget-amount"
            type="text"
            inputMode="decimal"
            className="input"
            required
            value={entryAmount}
            onChange={(e) => setEntryAmount(e.target.value)}
            placeholder="Ex.: 240,00"
          />
        </div>

        {entryKind === "expense" && (
          <>
            <div className="field">
              <label htmlFor="wa-budget-cat">Categoria</label>
              <select
                id="wa-budget-cat"
                className="input"
                value={entryCategoryId}
                onChange={(e) => setEntryCategoryId(e.target.value)}
              >
                <option value="">Sem categoria</option>
                {(budgetCtx?.categories ?? []).map((cat) => (
                  <option key={cat.id} value={cat.id}>
                    {cat.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="field">
              <label htmlFor="wa-budget-pay">Meio de pagamento</label>
              <select
                id="wa-budget-pay"
                className="input"
                value={entryPayment}
                onChange={(e) => {
                  setEntryPayment(e.target.value);
                  if (e.target.value === "credit") setEntryPaid(false);
                }}
              >
                <option value="pix">Pix</option>
                <option value="credit">Cartão de crédito</option>
                <option value="debit">Cartão de débito</option>
                <option value="boleto">Boleto</option>
                <option value="cash">Dinheiro</option>
              </select>
            </div>

            {entryPayment === "credit" && (
              <div className="field">
                <label htmlFor="wa-budget-card">Cartão de crédito</label>
                <select
                  id="wa-budget-card"
                  required
                  value={entryCardId}
                  onChange={(e) => setEntryCardId(e.target.value)}
                >
                  <option value="">Escolha o cartão</option>
                  {(budgetCtx?.cards ?? []).map((card) => (
                    <option key={card.id} value={card.id}>
                      {card.name}
                    </option>
                  ))}
                </select>
                <p className="muted small">A compra entra em aberto no mês da fatura do cartão.</p>
              </div>
            )}
            <label className="row small">
              <input
                type="checkbox"
                checked={entryPayment === "credit" ? false : entryPaid}
                disabled={entryPayment === "credit"}
                onChange={(e) => setEntryPaid(e.target.checked)}
              />
              Já está pago
            </label>
          </>
        )}

        {budgetMutation.isError && (
          <p className="alert alert--error" role="alert">
            {errorMessage(budgetMutation.error)}
          </p>
        )}
        {entryNotice && (
          <p className="alert alert--success" role="status">
            {entryNotice}
          </p>
        )}

        <div className="row row--right">
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            Cancelar
          </button>
          <button
            type="submit"
            className="btn btn--primary"
            disabled={!canSubmit}
          >
            {budgetMutation.isPending ? "Salvando…" : "Salvar no Meu Orçamento"}
          </button>
        </div>
      </form>
    </Sheet>
  );
}
