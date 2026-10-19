import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { CreditCard, Pencil, Plus, Trash2 } from "lucide-react";
import { useSearchParams } from "react-router";

import { useBudgetMutation } from "../api/budget";
import { errorMessage } from "../api/client";
import { extrasApi, extrasKeys, useCards, type Card, type CardSummary, type Invoice } from "../api/extras";
import { useAccounts } from "../api/money";
import { Bar, FormActions, MoneyInput } from "../components/budget";
import { EmptyGuide, Tip } from "../components/help";
import { Alert, Button, LoadingRegion, PageHeader, Sheet, Skeleton } from "../components/ui";
import { announce } from "../lib/announce";
import { money, moneyInput, monthLabel, parseMoney, shortDate } from "../lib/format";

const STATUS: Record<Invoice["status"], { label: string; tone: string }> = {
  open: { label: "Aberta", tone: "badge--neutral" },
  closed: { label: "Fechada · a pagar", tone: "badge--warn" },
  overdue: { label: "Atrasada", tone: "badge--error" },
  paid: { label: "Paga", tone: "badge--ok" },
};
const COLORS = ["#8a05be", "#ec7000", "#cc092f", "#1f7a62", "#24548f", "#17201c"];

function CardForm({ card, onDone }: { card?: Card; onDone: () => void }) {
  const [name, setName] = useState(card?.name ?? "");
  const [limit, setLimit] = useState(card?.limit_amount ? moneyInput(card.limit_amount) : "");
  const [closing, setClosing] = useState(String(card?.closing_day ?? ""));
  const [due, setDue] = useState(String(card?.due_day ?? ""));
  const [color, setColor] = useState(card?.color ?? COLORS[0]);
  const [accountId, setAccountId] = useState(card?.account_id ?? "");
  const accounts = useAccounts();
  const [error, setError] = useState("");
  const save = useBudgetMutation(async () => {
    const data = {
      name,
      limit_amount: limit.trim() ? parseMoney(limit) : null,
      closing_day: Number(closing),
      due_day: Number(due),
      color,
      account_id: accountId || null,
    };
    if (limit.trim() && !data.limit_amount) throw new Error("Limite inválido.");
    if (card) await extrasApi.updateCard(card.id, data);
    else await extrasApi.createCard(data);
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
      <div className="grid-2">
        <label>
          Nome do cartão
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Ex.: Nubank, Itaú Click" required maxLength={60} autoFocus />
        </label>
        <label>
          Limite (opcional)
          <MoneyInput value={limit} onChange={setLimit} placeholder="Ex.: 3.000,00" required={false} />
        </label>
        <label>
          <span className="field-label">
            Dia do fechamento <Tip>Dia de fechamento da fatura, informado pelo emissor. Compras a partir dele entram na fatura seguinte.</Tip>
          </span>
          <input type="number" inputMode="numeric" min={1} max={31} value={closing} onChange={(e) => setClosing(e.target.value)} placeholder="Ex.: 3" required />
        </label>
        <label>
          Dia do vencimento
          <input type="number" inputMode="numeric" min={1} max={31} value={due} onChange={(e) => setDue(e.target.value)} placeholder="Ex.: 10" required />
        </label>
      </div>
      {(accounts.data ?? []).length > 0 && (
        <label>
          <span className="field-label">
            Conta que paga a fatura <Tip>Ao marcar a fatura como paga, o valor sai do saldo desta conta.</Tip>
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
          {COLORS.map((c) => (
            <label key={c} className="color-dot" style={{ background: c }}>
              <input type="radio" name="color" checked={color === c} onChange={() => setColor(c)} aria-label={`Cor ${c}`} />
            </label>
          ))}
        </div>
      </fieldset>
      <FormActions loading={save.isPending} onCancel={onDone} label={card ? "Salvar" : "Adicionar cartão"} />
    </form>
  );
}

function InvoiceSheet({ summary, invoice, onClose }: { summary: CardSummary; invoice: Invoice | null; onClose: () => void }) {
  const card = summary.card;
  const items = useQuery({
    queryKey: ["budget", "cards", card.id, "items", invoice?.month],
    queryFn: () => extrasApi.invoiceItems(card.id, invoice!.month),
    enabled: !!invoice,
  });
  const pay = useBudgetMutation((paid: boolean) => extrasApi.payInvoice(card.id, invoice!.month, paid));
  return (
    <Sheet open={!!invoice} title={invoice ? `Fatura ${card.name} · ${monthLabel(invoice.month)}` : ""} onClose={onClose}>
      {invoice && (
        <div className="stack">
          <p className="muted small" style={{ margin: 0 }}>
            Fecha em {shortDate(invoice.closing_date)} · vence em {shortDate(invoice.due_date)} ·{" "}
            <span className={`badge ${STATUS[invoice.status].tone}`}>{STATUS[invoice.status].label}</span>
          </p>
          <strong className="quote__price">{money(invoice.total)}</strong>
          {items.isPending && <Skeleton height={120} />}
          {items.data && items.data.length === 0 && <p className="muted">Nenhuma compra nesta fatura.</p>}
          {items.data && items.data.length > 0 && (
            <ul className="items">
              {items.data.map((e) => (
                <li key={e.id} className="item">
                  <span className="item__main">
                    <span className="item__title">
                      {e.description}
                      {e.installment_total ? ` ${e.installment_number}/${e.installment_total}` : ""}
                    </span>
                    <span className="item__meta">compra em {shortDate(e.purchase_date)}</span>
                  </span>
                  <span className="item__amount">{money(e.amount)}</span>
                </li>
              ))}
            </ul>
          )}
          {invoice.count > 0 && (
            <Button
              type="button"
              variant={invoice.status === "paid" ? "secondary" : "primary"}
              loading={pay.isPending}
              onClick={() =>
                pay.mutate(invoice.status !== "paid", {
                  onSuccess: () => {
                    announce(invoice.status === "paid" ? "Fatura reaberta" : "Fatura paga");
                    onClose();
                  },
                })
              }
            >
              {invoice.status === "paid" ? "Desmarcar pagamento" : "Marcar fatura como paga"}
            </Button>
          )}
          <p className="muted small" style={{ margin: 0 }}>
            O pagamento da fatura marca as compras como pagas. Não registre o pagamento da fatura como nova despesa, para não contabilizar duas
            vezes.
          </p>
        </div>
      )}
    </Sheet>
  );
}

function CardTile({ summary, onEdit }: { summary: CardSummary; onEdit: () => void }) {
  const { card } = summary;
  const [open, setOpen] = useState<Invoice | null>(null);
  const invoices = useQuery({ queryKey: extrasKeys.invoices(card.id), queryFn: () => extrasApi.invoices(card.id) });
  const remove = useBudgetMutation(() => extrasApi.deleteCard(card.id));
  return (
    <section className="card stack card-tile" style={{ borderTopColor: card.color ?? undefined }}>
      <div className="section-header">
        <h2 className="row" style={{ gap: 8 }}>
          <CreditCard size={18} style={{ color: card.color ?? undefined }} aria-hidden /> {card.name}
        </h2>
        <span className="row" style={{ gap: 4 }}>
          <button type="button" className="icon-btn" aria-label={`Editar ${card.name}`} onClick={onEdit}>
            <Pencil size={16} />
          </button>
          <button
            type="button"
            className="icon-btn"
            aria-label={`Excluir ${card.name}`}
            onClick={() => window.confirm(`Excluir o cartão "${card.name}"? As compras continuam no orçamento.`) && remove.mutate(undefined)}
          >
            <Trash2 size={16} />
          </button>
        </span>
      </div>
      {card.limit_amount && (
        <div className="stack stack--tight">
          <Bar pct={summary.used_pct ?? 0} color={(summary.used_pct ?? 0) >= 90 ? "var(--error)" : card.color ?? undefined} />
          <div className="split small">
            <span>
              Usado <strong>{money(summary.used)}</strong>
            </span>
            <span>
              Disponível <strong>{money(summary.available)}</strong> de {money(card.limit_amount)}
            </span>
          </div>
        </div>
      )}
      <div className="stats">
        <button type="button" className="stat stat--button" onClick={() => setOpen(summary.open_invoice)}>
          <span className="stat__label">Fatura aberta</span>
          <strong className="stat__value">{money(summary.open_invoice.total)}</strong>
          <span className="muted small">fecha {shortDate(summary.open_invoice.closing_date)}</span>
        </button>
        {summary.closed_invoice && (
          <button type="button" className="stat stat--button" onClick={() => setOpen(summary.closed_invoice)}>
            <span className="stat__label">Fatura fechada</span>
            <strong className="stat__value">{money(summary.closed_invoice.total)}</strong>
            <span className={`badge ${STATUS[summary.closed_invoice.status].tone}`}>{STATUS[summary.closed_invoice.status].label}</span>
          </button>
        )}
        <div className="stat">
          <span className="stat__label">
            Melhor dia de compra <Tip>Compras feitas a partir deste dia entram na fatura seguinte, com prazo maior de pagamento.</Tip>
          </span>
          <strong className="stat__value">dia {summary.best_day}</strong>
          <span className="muted small">vence dia {card.due_day}</span>
        </div>
      </div>
      {invoices.data && (
        <div className="invoice-strip" role="list" aria-label="Faturas">
          {invoices.data
            .filter((i) => i.count > 0)
            .map((i) => (
              <button key={i.month} type="button" role="listitem" className="invoice-chip" onClick={() => setOpen(i)}>
                <span className="small">{monthLabel(i.month, true)}</span>
                <strong>{money(i.total)}</strong>
                <span className={`badge ${STATUS[i.status].tone}`}>{STATUS[i.status].label}</span>
              </button>
            ))}
        </div>
      )}
      <InvoiceSheet summary={summary} invoice={open} onClose={() => setOpen(null)} />
    </section>
  );
}

export default function CardsPage() {
  const cards = useCards();
  const [search, setSearch] = useSearchParams();
  const [adding, setAdding] = useState(() => search.get("novo") === "1");
  const [editing, setEditing] = useState<Card | null>(null);
  function closeAdd() {
    setAdding(false);
    if (search.get("novo")) setSearch({}, { replace: true });
  }
  return (
    <>
      <PageHeader
        title="Cartões de crédito"
        subtitle="Limite, faturas e melhor dia de compra. Compras no crédito são vinculadas à fatura correspondente."
        actions={
          <Button type="button" onClick={() => setAdding(true)}>
            <Plus size={16} /> Novo cartão
          </Button>
        }
      />
      {cards.isPending && (
        <LoadingRegion label="Carregando os cartões">
          <Skeleton height={200} />
        </LoadingRegion>
      )}
      {cards.isError && <Alert tone="error">{errorMessage(cards.error)}</Alert>}
      {cards.data && cards.data.length === 0 && (
        <section className="card">
          <EmptyGuide
            icon={<CreditCard size={22} />}
            title="Nenhum cartão ainda"
            text="Cadastre o cartão com os dias de fechamento e vencimento. Cada compra no crédito é alocada na fatura correta; parcelas, nas faturas seguintes."
            example={<>Ex.: “Nubank”, fecha dia 3, vence dia 10, limite R$ 3.000</>}
            action={
              <Button type="button" onClick={() => setAdding(true)}>
                <Plus size={16} /> Adicionar cartão
              </Button>
            }
          />
        </section>
      )}
      <div className="cards-grid">
        {cards.data?.map((s) => (
          <CardTile key={s.card.id} summary={s} onEdit={() => setEditing(s.card)} />
        ))}
      </div>
      <Sheet open={adding} title="Novo cartão" onClose={closeAdd}>
        {adding && <CardForm onDone={closeAdd} />}
      </Sheet>
      <Sheet open={!!editing} title="Editar cartão" onClose={() => setEditing(null)}>
        {editing && <CardForm card={editing} onDone={() => setEditing(null)} />}
      </Sheet>
    </>
  );
}
