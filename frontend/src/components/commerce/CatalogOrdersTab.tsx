import { CheckCircle2, ChevronDown, Search, ShoppingBag } from "lucide-react";

import type { CommercialOrder } from "../../api/commerce";
import { Badge, Bar, Stat } from "../budget";
import { EmptyGuide } from "../help";
import { formatQty, ORDER_STATUS_LABELS } from "../../lib/commerce";
import { money, plural, shortDate } from "../../lib/format";
import { normalizeText } from "../../lib/text";
import { Button } from "../ui";

export type OrderFilter = "all" | "confirmed" | "draft" | "cancelled";

const ORDER_FILTERS: { value: OrderFilter; label: string; test: (o: CommercialOrder) => boolean }[] = [
  { value: "all", label: "Todos", test: () => true },
  { value: "confirmed", label: "Confirmados", test: (o) => o.status === "confirmed" },
  { value: "draft", label: "Rascunhos", test: (o) => o.status === "draft" },
  { value: "cancelled", label: "Cancelados", test: (o) => o.status === "cancelled" },
];

/** Lista expansível e filtros dos pedidos comerciais com confirmação e cancelamento. */
export function CatalogOrdersTab({
  orders,
  search,
  onSearchChange,
  orderFilter,
  onOrderFilterChange,
  open,
  onToggleRow,
  onToggleAll,
  onOpenNewOrder,
  onConfirmOrder,
  onCancelOrder,
}: {
  orders: CommercialOrder[];
  search: string;
  onSearchChange: (value: string) => void;
  orderFilter: OrderFilter;
  onOrderFilterChange: (value: OrderFilter) => void;
  open: Set<string>;
  onToggleRow: (id: string) => void;
  onToggleAll: (ids: string[], allOpen: boolean) => void;
  onOpenNewOrder: () => void;
  onConfirmOrder: (id: string) => void;
  onCancelOrder: (id: string) => void;
}) {
  if (orders.length === 0) {
    return (
      <section className="card">
        <EmptyGuide
          icon={<ShoppingBag size={22} />}
          title="Nenhum pedido registrado ainda"
          text="Monte um pedido escolhendo itens do catálogo. Ao confirmar, o estoque é atualizado na hora, o negócio pode ir como Ganho no CRM e o valor entra nas receitas do Meu Orçamento."
          example={<>Ex.: Pedido de 2 painéis LED para “Cliente Ana” (R$ 400) já integrado ao mês.</>}
          action={
            <Button type="button" onClick={onOpenNewOrder}>
              <ShoppingBag size={16} /> Novo pedido
            </Button>
          }
        />
      </section>
    );
  }

  const needle = normalizeText(search);
  const shownOrders = orders.filter((o) => {
    const rule = ORDER_FILTERS.find((f) => f.value === orderFilter)!;
    const code = String(o.number).padStart(4, "0");
    return rule.test(o) && (!needle || normalizeText(`${code} ${o.customer_name}`).includes(needle));
  });
  const allOpen = shownOrders.length > 0 && shownOrders.every((o) => open.has(o.id));

  return (
    <>
      <div className="list-tools list-tools--pills person-tools" role="search" aria-label="Filtrar pedidos">
        <label className="list-tools__search">
          <Search size={16} aria-hidden />
          <span className="sr-only">Buscar pedido ou cliente</span>
          <input
            type="search"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Buscar por cliente ou #número..."
          />
        </label>
        <span className="pill-group" role="group" aria-label="Status do pedido">
          {ORDER_FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              className="chip-btn"
              aria-pressed={orderFilter === f.value}
              onClick={() => onOrderFilterChange(f.value)}
            >
              {f.label} ({orders.filter(f.test).length})
            </button>
          ))}
        </span>
        <button
          type="button"
          className="chip-btn person-tools__all"
          aria-pressed={allOpen}
          onClick={() => onToggleAll(shownOrders.map((o) => o.id), allOpen)}
        >
          {allOpen ? "Fechar todos" : "Abrir todos"}
        </button>
      </div>

      {shownOrders.length === 0 ? (
        <p className="muted">Nenhum pedido encontrado com esse filtro.</p>
      ) : (
        <div className="person-rows">
          {shownOrders.map((o) => {
            const isOpen = open.has(o.id);
            const code = String(o.number).padStart(4, "0");
            const totalNum = Number(o.total_amount);
            const profitPct =
              totalNum > 0 ? Math.max(4, Math.min(100, (Number(o.gross_profit) / totalNum) * 100)) : 0;
            return (
              <article
                key={o.id}
                className={`card person-row ${isOpen ? "is-open" : ""}`}
                data-order-row={o.id}
              >
                <button
                  type="button"
                  className="person-row__head"
                  aria-expanded={isOpen}
                  onClick={() => onToggleRow(o.id)}
                >
                  <span className="person-row__avatar" aria-hidden>
                    <ShoppingBag size={18} />
                  </span>
                  <span className="person-row__who">
                    <strong>
                      Pedido #{code} · {o.customer_name}
                    </strong>
                    <span className="muted small">
                      {ORDER_STATUS_LABELS[o.status]} · {o.items.length} {plural(o.items.length, "item", "itens")} ·{" "}
                      {shortDate(o.created_at.slice(0, 10))}
                    </span>
                  </span>
                  <span className="person-row__progress">
                    <span className="person-row__bar">
                      <Bar
                        pct={o.status === "cancelled" ? 0 : profitPct}
                        color={o.status === "draft" ? "var(--warn)" : undefined}
                      />
                    </span>
                    <span className="muted small">Lucro bruto {money(o.gross_profit)}</span>
                  </span>
                  <span className="person-row__balance">
                    <strong className={o.status === "cancelled" ? "muted" : "tone--ok"}>
                      {money(o.total_amount)}
                    </strong>
                  </span>
                  <span className="person-row__chev" aria-hidden>
                    <ChevronDown size={18} />
                  </span>
                </button>

                {isOpen && (
                  <div className="person-row__body">
                    <div className="row">
                      <Badge tone={o.status === "confirmed" ? "accent" : o.status === "draft" ? "warn" : "neutral"}>
                        {ORDER_STATUS_LABELS[o.status]}
                      </Badge>
                      {o.budget_income_id && <Badge tone="accent">Receita no Orçamento</Badge>}
                      {o.crm_deal_id && <Badge tone="accent">Ganho no CRM</Badge>}
                    </div>

                    <div className="stats">
                      <Stat label="Total vendido" value={money(o.total_amount)} tone="ok" />
                      <Stat label="Desconto" value={money(o.discount)} />
                      <Stat label="Custo dos itens" value={money(o.total_cost)} />
                      <Stat label="Lucro bruto" value={money(o.gross_profit)} tone="ok" />
                    </div>

                    <ul className="items">
                      {o.items.map((it, idx) => (
                        <li key={idx} className="item">
                          <span className="item__main">
                            <strong className="item__title">{it.name}</strong>
                            <span className="item__meta">
                              {formatQty(it.qty)} {it.unit ?? "un"} × {money(it.unit_price)}
                            </span>
                          </span>
                          <span className="item__value">
                            {money((Number(it.qty) || 0) * (Number(it.unit_price) || 0))}
                          </span>
                        </li>
                      ))}
                    </ul>

                    {o.notes && <p className="muted small">{o.notes}</p>}

                    {o.status !== "cancelled" && (
                      <div className="person-row__actions">
                        {o.status === "draft" && (
                          <button
                            type="button"
                            className="btn btn--primary btn--sm"
                            onClick={() => onConfirmOrder(o.id)}
                          >
                            <CheckCircle2 size={14} /> Confirmar e integrar
                          </button>
                        )}
                        <button
                          type="button"
                          className="btn btn--secondary btn--sm"
                          onClick={() => onCancelOrder(o.id)}
                        >
                          Cancelar pedido
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </article>
            );
          })}
        </div>
      )}
    </>
  );
}
