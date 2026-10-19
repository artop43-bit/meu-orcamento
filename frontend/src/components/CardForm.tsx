import { useState, type FormEvent } from "react";

import { useBudgetMutation } from "../api/budget";
import { errorMessage } from "../api/client";
import { CARD_KIND_LABEL, extrasApi, type Card, type CardKind } from "../api/extras";
import { useAccounts } from "../api/money";
import { moneyInput, parseMoney } from "../lib/format";
import { FormActions, MoneyInput } from "./budget";
import { DayField } from "./DateField";
import { Tip } from "./help";
import { Alert } from "./ui";

export const CARD_COLORS = ["#8a05be", "#ec7000", "#cc092f", "#1f7a62", "#24548f", "#17201c"];

/**
 * Cadastro do cartão. A função define o que aparece: crédito pede limite, fechamento e
 * vencimento da fatura; débito só a conta de onde o dinheiro sai.
 */
export function CardForm({
  card,
  defaultKind = "credit",
  onDone,
}: {
  card?: Card;
  defaultKind?: CardKind;
  onDone: (created?: Card) => void;
}) {
  const [name, setName] = useState(card?.name ?? "");
  const [kind, setKind] = useState<CardKind>(card?.kind ?? defaultKind);
  const [limit, setLimit] = useState(card?.limit_amount ? moneyInput(card.limit_amount) : "");
  const [closing, setClosing] = useState(card?.closing_day ? String(card.closing_day) : "");
  const [due, setDue] = useState(card?.due_day ? String(card.due_day) : "");
  const [color, setColor] = useState(card?.color ?? CARD_COLORS[0]);
  const [accountId, setAccountId] = useState(card?.account_id ?? "");
  const accounts = useAccounts();
  const [error, setError] = useState("");
  const credit = kind !== "debit";

  const save = useBudgetMutation(async () => {
    const data = {
      name,
      kind,
      limit_amount: credit && limit.trim() ? parseMoney(limit) : null,
      closing_day: credit ? Number(closing) : null,
      due_day: credit ? Number(due) : null,
      color,
      account_id: accountId || null,
    };
    if (credit && limit.trim() && !data.limit_amount) throw new Error("Limite inválido.");
    return card ? extrasApi.updateCard(card.id, data) : extrasApi.createCard(data);
  });

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const saved = await save.mutateAsync(undefined);
      onDone(saved);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  const accountLabel = kind === "debit" ? "Conta do débito" : kind === "both" ? "Conta vinculada" : "Conta que paga a fatura";
  const accountTip =
    kind === "debit"
      ? "As compras no débito saem do saldo desta conta na hora."
      : kind === "both"
        ? "As compras no débito e o pagamento da fatura saem do saldo desta conta."
        : "Ao marcar a fatura como paga, o valor sai do saldo desta conta.";

  return (
    <form className="inline-form" onSubmit={submit}>
      <Alert tone="error">{error}</Alert>
      <label>
        Nome do cartão
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Ex.: Nubank, Itaú Click" required maxLength={60} autoFocus />
      </label>
      <fieldset className="radios">
        <legend className="field-label">
          Função <Tip>Crédito: compras vão para a fatura e usam o limite. Débito: saem na hora da conta, sem fatura e sem limite.</Tip>
        </legend>
        <div className="segmented segmented--3">
          {(Object.keys(CARD_KIND_LABEL) as CardKind[]).map((value) => (
            <label key={value}>
              <input type="radio" name="card-kind" checked={kind === value} onChange={() => setKind(value)} />
              {CARD_KIND_LABEL[value]}
            </label>
          ))}
        </div>
      </fieldset>
      {credit && (
        <>
          <label>
            Limite (opcional)
            <MoneyInput value={limit} onChange={setLimit} placeholder="Ex.: 3.000,00" required={false} />
          </label>
          <div className="grid-2 grid-2--even">
            <label>
              <span className="field-label">
                Dia do fechamento <Tip>Dia de fechamento da fatura, informado pelo emissor. Compras a partir dele entram na fatura seguinte.</Tip>
              </span>
              <DayField value={closing} onChange={setClosing} recurring required />
            </label>
            <label>
              <span className="field-label">Dia do vencimento</span>
              <DayField value={due} onChange={setDue} recurring required />
            </label>
          </div>
        </>
      )}
      {(accounts.data ?? []).length > 0 && (
        <label>
          <span className="field-label">
            {accountLabel} <Tip>{accountTip}</Tip>
          </span>
          <select value={accountId} onChange={(e) => setAccountId(e.target.value)}>
            <option value="">Não informar</option>
            {(accounts.data ?? []).map((b) => (
              <option key={b.account.id} value={b.account.id}>
                {b.account.name}
              </option>
            ))}
          </select>
        </label>
      )}
      <fieldset className="radios">
        <legend className="field-label">Cor</legend>
        <div className="chips">
          {CARD_COLORS.map((c) => (
            <label key={c} className="color-dot" style={{ background: c }}>
              <input type="radio" name="color" checked={color === c} onChange={() => setColor(c)} aria-label={`Cor ${c}`} />
            </label>
          ))}
        </div>
      </fieldset>
      <FormActions loading={save.isPending} onCancel={() => onDone()} label={card ? "Salvar" : "Adicionar cartão"} />
    </form>
  );
}
