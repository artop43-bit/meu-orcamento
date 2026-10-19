import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CreditCard, Pencil, Plus, Trash2 } from "lucide-react";
import { useSearchParams } from "react-router";

import { useBudgetMutation } from "../api/budget";
import { errorMessage } from "../api/client";
import { CARD_KIND_LABEL, extrasApi, extrasKeys, hasCredit, useCards, type Card, type CardSummary, type Invoice } from "../api/extras";
import { useAccounts } from "../api/money";
import { Bar } from "../components/budget";
import { CardForm } from "../components/CardForm";
import { EmptyGuide, Tip } from "../components/help";
import { Alert, Button, LoadingRegion, PageHeader, Sheet, Skeleton } from "../components/ui";
import { announce } from "../lib/announce";
import { money, monthLabel, shortDate } from "../lib/format";

const STATUS: Record<Invoice["status"], { label: string; tone: string }> = {
  open: { label: "Aberta", tone: "badge--neutral" },
  closed: { label: "Fechada · a pagar", tone: "badge--warn" },
  overdue: { label: "Atrasada", tone: "badge--error" },
  paid: { label: "Paga", tone: "badge--ok" },
};
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
  const credit = hasCredit(card);
  const accounts = useAccounts();
  const account = accounts.data?.find((b) => b.account.id === card.account_id)?.account;
  const invoices = useQuery({ queryKey: extrasKeys.invoices(card.id), queryFn: () => extrasApi.invoices(card.id), enabled: credit });
  const remove = useBudgetMutation(() => extrasApi.deleteCard(card.id));
  return (
    <section className="card stack card-tile" style={{ borderTopColor: card.color ?? undefined }}>
      <div className="section-header">
        <h2 className="row" style={{ gap: 8 }}>
          <CreditCard size={18} style={{ color: card.color ?? undefined }} aria-hidden /> {card.name}
          <span className="badge">{CARD_KIND_LABEL[card.kind]}</span>
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
      {!credit && (
        <p className="muted" style={{ margin: 0 }}>
          Compras no débito entram pagas e saem {account ? <strong>da conta {account.name}</strong> : "da conta vinculada"} na hora. Não usam limite
          nem fatura.
        </p>
      )}
      {credit && summary.open_invoice && (
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
      )}
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
        title="Cartões"
        subtitle="Crédito: limite, faturas e melhor dia de compra. Débito: compras saem na hora da conta vinculada."
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
            text="Cadastre os cartões de crédito (com fechamento e vencimento) e de débito. No crédito, cada compra vai para a fatura certa; no débito, sai na hora da conta."
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
        {adding && <CardForm onDone={() => closeAdd()} />}
      </Sheet>
      <Sheet open={!!editing} title="Editar cartão" onClose={() => setEditing(null)}>
        {editing && <CardForm card={editing} onDone={() => setEditing(null)} />}
      </Sheet>
    </>
  );
}
