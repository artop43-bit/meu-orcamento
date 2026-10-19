import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowRightLeft, Landmark, Pencil, Plus, Trash2 } from "lucide-react";

import { useBudgetMutation } from "../api/budget";
import { errorMessage } from "../api/client";
import { ACCOUNT_KINDS, moneyApi, useAccounts, type Account, type AccountKind } from "../api/money";
import { FormActions, MoneyInput, requireMoney } from "../components/budget";
import { DateField } from "../components/DateField";
import { EmptyGuide, Tip } from "../components/help";
import { Alert, Button, Kpi, LoadingRegion, PageHeader, Sheet, Skeleton } from "../components/ui";
import { money, moneyInput, parseMoney, shortDate, todayISO } from "../lib/format";

function AccountForm({ account, onDone }: { account?: Account; onDone: () => void }) {
  const [name, setName] = useState(account?.name ?? "");
  const [kind, setKind] = useState<AccountKind>(account?.kind ?? "checking");
  const [initial, setInitial] = useState(account ? moneyInput(account.initial_balance) : "");
  const [error, setError] = useState("");
  const save = useBudgetMutation(async () => {
    const raw = initial.trim();
    const negative = raw.startsWith("-");
    const parsed = raw ? parseMoney(raw.replace("-", "")) : "0.00";
    if (parsed === null) throw new Error("Saldo inicial inválido.");
    const data = { name, kind, initial_balance: negative ? `-${parsed}` : parsed };
    if (account) await moneyApi.updateAccount(account.id, data);
    else await moneyApi.createAccount(data);
  });
  async function submit(e: FormEvent) {
    e.preventDefault();
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
      <label>
        Nome
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Ex.: Nubank, Itaú, Carteira" required maxLength={60} autoFocus />
      </label>
      <label>
        Tipo
        <select value={kind} onChange={(e) => setKind(e.target.value as AccountKind)}>
          {Object.entries(ACCOUNT_KINDS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span className="field-label">
          Saldo atual <Tip>Saldo da conta hoje, conforme o extrato do banco. A partir dele, o app soma receitas e subtrai despesas.</Tip>
        </span>
        <input inputMode="decimal" value={initial} onChange={(e) => setInitial(e.target.value)} placeholder="0,00" />
      </label>
      <FormActions loading={save.isPending} onCancel={onDone} label={account ? "Salvar" : "Adicionar conta"} />
    </form>
  );
}

function TransferForm({ accounts, onDone }: { accounts: Account[]; onDone: () => void }) {
  const [from, setFrom] = useState(accounts[0]?.id ?? "");
  const [to, setTo] = useState(accounts[1]?.id ?? "");
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState(todayISO());
  const [error, setError] = useState("");
  const save = useBudgetMutation(() =>
    moneyApi.createTransfer({ from_account_id: from, to_account_id: to, amount: requireMoney(amount), date, notes: null }),
  );
  async function submit(e: FormEvent) {
    e.preventDefault();
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
          De
          <select value={from} onChange={(e) => setFrom(e.target.value)}>
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Para
          <select value={to} onChange={(e) => setTo(e.target.value)}>
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Valor
          <MoneyInput value={amount} onChange={setAmount} placeholder="0,00" />
        </label>
        <label>
          Data
          <DateField value={date} onChange={setDate} required />
        </label>
      </div>
      <p className="muted small" style={{ margin: 0 }}>
        Transferências entre contas não entram como receita nem despesa.
      </p>
      <FormActions loading={save.isPending} onCancel={onDone} label="Transferir" />
    </form>
  );
}

export default function AccountsPage() {
  const accounts = useAccounts();
  const transfers = useQuery({ queryKey: ["budget", "transfers"], queryFn: () => moneyApi.transfers() });
  const [editing, setEditing] = useState<Account | "new" | null>(null);
  const [transferring, setTransferring] = useState(false);
  const remove = useBudgetMutation((id: string) => moneyApi.deleteAccount(id));
  const removeTransfer = useBudgetMutation((id: string) => moneyApi.deleteTransfer(id));
  const list = accounts.data ?? [];
  const names = new Map(list.map((b) => [b.account.id, b.account.name]));
  const total = list.reduce((s, b) => s + Number(b.balance), 0);
  const totalEnd = list.reduce((s, b) => s + Number(b.end_of_month), 0);

  return (
    <>
      <PageHeader
        title="Contas"
        subtitle="Saldo de cada conta hoje e a previsão para o fim do mês."
        actions={
          <span className="row">
            {list.length > 1 && (
              <Button type="button" variant="secondary" onClick={() => setTransferring(true)}>
                <ArrowRightLeft size={16} /> Transferir
              </Button>
            )}
            <Button type="button" onClick={() => setEditing("new")}>
              <Plus size={16} /> Nova conta
            </Button>
          </span>
        }
      />
      {accounts.isPending && (
        <LoadingRegion label="Carregando as contas">
          <Skeleton height={160} />
        </LoadingRegion>
      )}
      {accounts.isError && <Alert tone="error">{errorMessage(accounts.error)}</Alert>}
      {accounts.data && list.length === 0 && (
        <section className="card">
          <EmptyGuide
            icon={<Landmark size={22} />}
            title="Nenhuma conta cadastrada"
            text="Cadastre suas contas com o saldo atual. Ao lançar despesas e receitas indicando a conta, o saldo de cada uma é atualizado automaticamente."
            action={
              <Button type="button" onClick={() => setEditing("new")}>
                <Plus size={16} /> Adicionar conta
              </Button>
            }
          />
        </section>
      )}
      {list.length > 0 && (
        <div className="stack" style={{ gap: 20 }}>
          <div className="kpis kpis--3">
            <Kpi icon={<Landmark size={17} />} label="Saldo total hoje" value={money(total)} foot={`${list.length} conta(s)`} />
            <Kpi
              icon={<Landmark size={17} />}
              tone={totalEnd < 0 ? "expense" : "accent"}
              label="Previsto para o fim do mês"
              value={money(totalEnd)}
              valueClass={totalEnd < 0 ? "tone--error" : undefined}
              foot="Considera receitas e despesas pendentes"
            />
          </div>
          <section className="card stack">
            <h2>Saldos</h2>
            <ul className="items">
              {list.map(({ account, balance, end_of_month }) => (
                <li key={account.id} className="item">
                  <span className="item__main">
                    <span className="item__title">{account.name}</span>
                    <span className="item__meta">
                      {ACCOUNT_KINDS[account.kind]} · fim do mês: {money(end_of_month)}
                    </span>
                  </span>
                  <strong className={`item__amount ${Number(balance) < 0 ? "tone--error" : ""}`}>{money(balance)}</strong>
                  <span className="row" style={{ gap: 2 }}>
                    <button type="button" className="icon-btn" aria-label={`Editar ${account.name}`} onClick={() => setEditing(account)}>
                      <Pencil size={16} />
                    </button>
                    <button
                      type="button"
                      className="icon-btn"
                      aria-label={`Excluir ${account.name}`}
                      onClick={() =>
                        window.confirm(`Excluir a conta "${account.name}"? Os lançamentos continuam no orçamento, sem conta vinculada.`) &&
                        remove.mutate(account.id)
                      }
                    >
                      <Trash2 size={16} />
                    </button>
                  </span>
                </li>
              ))}
            </ul>
          </section>
          {transfers.data && transfers.data.length > 0 && (
            <section className="card stack">
              <h2>Transferências</h2>
              <ul className="items">
                {transfers.data.map((t) => (
                  <li key={t.id} className="item">
                    <span className="item__main">
                      <span className="item__title">
                        {names.get(t.from_account_id)} → {names.get(t.to_account_id)}
                      </span>
                      <span className="item__meta">{shortDate(t.date)}</span>
                    </span>
                    <span className="item__amount">{money(t.amount)}</span>
                    <button type="button" className="icon-btn" aria-label="Excluir transferência" onClick={() => removeTransfer.mutate(t.id)}>
                      <Trash2 size={16} />
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
      <Sheet open={editing !== null} title={editing === "new" ? "Nova conta" : "Editar conta"} onClose={() => setEditing(null)}>
        {editing !== null && <AccountForm account={editing === "new" ? undefined : editing} onDone={() => setEditing(null)} />}
      </Sheet>
      <Sheet open={transferring} title="Transferência entre contas" onClose={() => setTransferring(false)}>
        {transferring && <TransferForm accounts={list.map((b) => b.account)} onDone={() => setTransferring(false)} />}
      </Sheet>
    </>
  );
}
