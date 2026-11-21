import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowDownUp,
  BadgeDollarSign,
  Boxes,
  ChevronDown,
  Package,
  Pencil,
  Plus,
  Search,
  ShoppingBag,
  Trash2,
  TrendingUp,
  Wrench,
} from "lucide-react";

import { errorMessage } from "../../api/client";
import {
  catalogApi,
  useCatalogBridges,
  useCatalogItems,
  useCatalogMovements,
  useCatalogOrders,
  type CatalogItem,
} from "../../api/commerce";
import { Badge, Bar, Stat } from "../../components/budget";
import { CatalogItemSheet } from "../../components/commerce/CatalogItemSheet";
import { CatalogOrdersTab, type OrderFilter } from "../../components/commerce/CatalogOrdersTab";
import { NewOrderSheet } from "../../components/commerce/NewOrderSheet";
import { StockMoveSheet } from "../../components/commerce/StockMoveSheet";
import { EmptyGuide, Tip } from "../../components/help";
import { Alert, Button, LoadingRegion, PageHeader, Sheet, Skeleton } from "../../components/ui";
import { useUndo } from "../../components/undo";
import { formatQty, MOVEMENT_KIND_LABELS } from "../../lib/commerce";
import { formatDateHeading, money, plural, shortDate } from "../../lib/format";
import { normalizeText } from "../../lib/text";
import type { CommercialOrder } from "../../api/commerce";

type ItemFilter = "all" | "product" | "service" | "low";

const UNIT_NAMES: Record<string, string> = { un: "unidade", kg: "quilo", h: "hora" };

const ITEM_FILTERS: { value: ItemFilter; label: string; test: (it: CatalogItem) => boolean }[] = [
  { value: "all", label: "Todos", test: () => true },
  { value: "product", label: "Produtos", test: (it) => it.kind === "product" },
  { value: "service", label: "Serviços", test: (it) => it.kind === "service" },
  { value: "low", label: "Repor estoque", test: (it) => it.low_stock },
];

export default function CatalogPage({ tab }: { tab: "items" | "orders" }) {
  const qc = useQueryClient();
  const undo = useUndo();
  const [itemFilter, setItemFilter] = useState<ItemFilter>("all");
  const [orderFilter, setOrderFilter] = useState<OrderFilter>("all");
  const [search, setSearch] = useState("");
  const [openedIds, setOpenedIds] = useState<Set<string> | null>(null);

  const itemsQuery = useCatalogItems("", "");
  const movementsQuery = useCatalogMovements();
  const ordersQuery = useCatalogOrders();

  const [itemOpen, setItemOpen] = useState(false);
  const [editing, setEditing] = useState<CatalogItem | null>(null);
  const [moveTarget, setMoveTarget] = useState<CatalogItem | null>(null);
  const [orderOpen, setOrderOpen] = useState(false);
  const [orderPresetItem, setOrderPresetItem] = useState<CatalogItem | undefined>(undefined);
  const [confirmTarget, setConfirmTarget] = useState<CommercialOrder | null>(null);
  const [confirmSyncBudget, setConfirmSyncBudget] = useState(true);
  const [confirmSyncCrm, setConfirmSyncCrm] = useState(true);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [feedbackTone, setFeedbackTone] = useState<"info" | "error">("info");

  const bridges = useCatalogBridges(orderOpen).data;

  const allItems = (itemsQuery.data?.items ?? []).filter((it) => !undo.isHidden(it.id));
  const summary = itemsQuery.data?.summary;
  const movements = movementsQuery.data ?? [];
  const orders = ordersQuery.data ?? [];

  const firstRowId = tab === "items" ? allItems[0]?.id : orders[0]?.id;
  useEffect(() => {
    setOpenedIds(null);
  }, [tab]);
  useEffect(() => {
    if (openedIds === null && firstRowId) {
      setOpenedIds(new Set([firstRowId]));
    }
  }, [openedIds, firstRowId]);

  const open = openedIds ?? new Set(firstRowId ? [firstRowId] : []);

  function toggleRow(id: string) {
    const next = new Set(open);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setOpenedIds(next);
  }

  function invalidateAll() {
    void qc.invalidateQueries({ queryKey: ["catalog"] });
    void qc.invalidateQueries({ queryKey: ["crm", "sources"] });
  }

  function openNewItem() {
    setEditing(null);
    setItemOpen(true);
  }

  function openEditItem(it: CatalogItem) {
    setEditing(it);
    setItemOpen(true);
  }

  function openNewOrder(presetItem?: CatalogItem) {
    setOrderPresetItem(presetItem);
    setOrderOpen(true);
  }

  function deleteItemWithUndo(it: CatalogItem) {
    undo.remove({
      ids: [it.id],
      message: `${it.name} excluído`,
      commit: async () => {
        await catalogApi.deleteItem(it.id);
        invalidateAll();
      },
    });
  }

  const confirmOrder = useMutation({
    mutationFn: ({ id, syncBudget, syncCrm }: { id: string; syncBudget: boolean; syncCrm: boolean }) =>
      catalogApi.confirmOrder(id, { sync_budget: syncBudget, sync_crm: syncCrm }),
    onSuccess: (order, vars) => {
      setConfirmTarget(null);
      invalidateAll();
      setFeedbackTone("info");
      const parts = [
        vars.syncBudget ? "receita no Meu Orçamento" : null,
        vars.syncCrm ? "negócio no CRM" : null,
      ].filter(Boolean);
      const tail = parts.length > 0 ? ` e integrado (${parts.join(" + ")})` : "";
      setFeedback(`Pedido #${String(order.number).padStart(4, "0")} confirmado${tail}.`);
    },
    onError: (e) => {
      setFeedbackTone("error");
      setFeedback(errorMessage(e));
    },
  });

  function openConfirmDialog(id: string) {
    const found = orders.find((o) => o.id === id) ?? null;
    setConfirmTarget(found);
    setConfirmSyncBudget(true);
    setConfirmSyncCrm(true);
  }

  const cancelOrder = useMutation({
    mutationFn: catalogApi.cancelOrder,
    onSuccess: (order) => {
      invalidateAll();
      if (order.warning) {
        setFeedbackTone("error");
        setFeedback(`Pedido #${String(order.number).padStart(4, "0")} cancelado. ${order.warning}`);
      } else {
        setFeedbackTone("info");
        setFeedback(`Pedido #${String(order.number).padStart(4, "0")} cancelado.`);
      }
    },
    onError: (e) => {
      setFeedbackTone("error");
      setFeedback(errorMessage(e));
    },
  });

  const needle = normalizeText(search);
  const shownItems = allItems.filter((it) => {
    const rule = ITEM_FILTERS.find((f) => f.value === itemFilter)!;
    return rule.test(it) && (!needle || normalizeText(`${it.name} ${it.sku ?? ""}`).includes(needle));
  });
  const allItemsOpen = shownItems.length > 0 && shownItems.every((it) => open.has(it.id));

  const confirmedOrders = orders.filter((o) => o.status === "confirmed");
  const confirmedTotal = confirmedOrders.reduce((acc, o) => acc + Number(o.total_amount), 0);
  const confirmedProfit = confirmedOrders.reduce((acc, o) => acc + Number(o.gross_profit), 0);
  const confirmedShare = orders.length > 0 ? Math.round((confirmedOrders.length / orders.length) * 100) : 0;

  const healthyProducts = summary
    ? Math.max(0, summary.active_products - summary.low_stock_count)
    : 0;
  const stockHealthPct =
    summary && summary.active_products > 0
      ? Math.round((healthyProducts / summary.active_products) * 100)
      : 100;

  return (
    <div className="stack">
      <PageHeader
        title={tab === "items" ? "Itens e estoque" : "Pedidos e vendas"}
        subtitle={
          tab === "items"
            ? "Controle produtos, serviços, custos, margens e saldo com baixa automática nos pedidos."
            : "Monte pedidos com itens do catálogo e lance receita no Meu Orçamento e no Funil do CRM."
        }
        actions={
          <div className="row">
            <Button type="button" variant="secondary" onClick={() => openNewOrder()}>
              <ShoppingBag size={16} /> Novo pedido
            </Button>
            <Button type="button" onClick={openNewItem}>
              <Plus size={16} /> Novo item
            </Button>
          </div>
        }
      />

      {feedback && (
        <Alert tone={feedbackTone}>
          <div className="split">
            <span>{feedback}</span>
            <button
              type="button"
              className="btn btn--secondary btn--sm"
              onClick={() => {
                setFeedback(null);
                setFeedbackTone("info");
              }}
            >
              Fechar
            </button>
          </div>
        </Alert>
      )}

      {itemsQuery.isPending && (
        <LoadingRegion label="Carregando o catálogo">
          <Skeleton height={160} />
        </LoadingRegion>
      )}
      {itemsQuery.isError && <Alert tone="error">{errorMessage(itemsQuery.error)}</Alert>}

      {summary && (
        <div className="greeting">
          <span className="greeting__date">{formatDateHeading()}</span>
          <p className="greeting__hello">
            {tab === "items"
              ? `Você acompanha ${summary.total_items} ${plural(summary.total_items, "item ativo", "itens ativos")} entre produtos e serviços.`
              : `Você tem ${orders.length} ${plural(orders.length, "pedido registrado", "pedidos registrados")}.`}
          </p>
          <p className="greeting__text">
            {summary.low_stock_count > 0
              ? `${summary.low_stock_count} ${plural(summary.low_stock_count, "produto chegou", "produtos chegaram")} ao estoque mínimo.`
              : "Todos os produtos monitorados estão com estoque confortável no momento."}
          </p>
        </div>
      )}

      {summary && tab === "items" && (
        <section className="card month-summary" aria-label="Resumo do catálogo e estoque">
          <div className="month-summary__main">
            <span className="month-summary__label">
              <BadgeDollarSign size={15} aria-hidden /> Potencial de venda em estoque
            </span>
            <strong className="month-summary__value tone--ok">
              {money(summary.stock_sale_value)}
            </strong>
            <span className="muted small">
              Custo investido de {money(summary.stock_cost_value)} nos itens estocados
            </span>
          </div>
          <div className="month-summary__side">
            <dl className="month-summary__grid">
              <div>
                <dt>
                  <Package size={14} aria-hidden /> Produtos
                </dt>
                <dd className="month-summary__num">{summary.active_products}</dd>
                <dd className="month-summary__foot">{healthyProducts} com saldo bom</dd>
              </div>
              <div>
                <dt>
                  <Wrench size={14} aria-hidden /> Serviços
                </dt>
                <dd className="month-summary__num">{summary.active_services}</dd>
                <dd className="month-summary__foot">Mão de obra e pacotes</dd>
              </div>
              <div>
                <dt>
                  <AlertTriangle size={14} aria-hidden /> Repor estoque
                </dt>
                <dd className={`month-summary__num ${summary.low_stock_count > 0 ? "tone--error" : ""}`}>
                  {summary.low_stock_count}
                </dd>
                <dd className="month-summary__foot">
                  {summary.low_stock_count > 0 ? "Abaixo do mínimo" : "Tudo em dia"}
                </dd>
              </div>
            </dl>
            <div
              className={`month-summary__bar ${summary.low_stock_count > 0 ? "is-high" : ""}`}
              role="img"
              aria-label={`${stockHealthPct}% dos produtos acima do estoque mínimo`}
            >
              <span style={{ width: `${stockHealthPct}%` }} />
            </div>
          </div>
        </section>
      )}

      {summary && tab === "orders" && (
        <section className="card month-summary" aria-label="Resumo dos pedidos">
          <div className="month-summary__main">
            <span className="month-summary__label">
              <TrendingUp size={15} aria-hidden /> Faturamento confirmado
            </span>
            <strong className="month-summary__value tone--ok">{money(confirmedTotal)}</strong>
            <span className="muted small">
              Lucro bruto estimado de {money(confirmedProfit)} após custos do catálogo
            </span>
          </div>
          <div className="month-summary__side">
            <dl className="month-summary__grid">
              <div>
                <dt>Confirmados</dt>
                <dd className="month-summary__num">{confirmedOrders.length}</dd>
                <dd className="month-summary__foot">Baixa automática aplicada</dd>
              </div>
              <div>
                <dt>Rascunhos</dt>
                <dd className="month-summary__num">
                  {orders.filter((o) => o.status === "draft").length}
                </dd>
                <dd className="month-summary__foot">Aguardando fechamento</dd>
              </div>
              <div>
                <dt>Conversão</dt>
                <dd className="month-summary__num">{confirmedShare}%</dd>
                <dd className="month-summary__foot">Dos pedidos registrados</dd>
              </div>
            </dl>
            <div
              className="month-summary__bar"
              role="img"
              aria-label={`${confirmedShare}% dos pedidos confirmados`}
            >
              <span style={{ width: `${confirmedShare}%` }} />
            </div>
          </div>
        </section>
      )}

      {tab === "items" && (
        <>
          {allItems.length === 0 ? (
            <section className="card">
              <EmptyGuide
                icon={<Boxes size={22} />}
                title="Seu catálogo ainda está vazio"
                text="Cadastre aqui os produtos que você vende ou os serviços que presta. Ao fechar um pedido, o estoque baixa sozinho e o ganho pode ir direto para o Meu Orçamento."
                example={<>Ex.: “Painel LED 50W” (custo R$ 80, venda R$ 200, mínimo 2 un) ou “Consultoria mensal” (serviço R$ 1.500).</>}
                action={
                  <Button type="button" onClick={openNewItem}>
                    <Plus size={16} /> Novo item
                  </Button>
                }
              />
            </section>
          ) : (
            <>
              <div className="list-tools list-tools--pills person-tools" role="search" aria-label="Filtrar catálogo">
                <label className="list-tools__search">
                  <Search size={16} aria-hidden />
                  <span className="sr-only">Buscar item ou SKU</span>
                  <input
                    type="search"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Buscar item ou SKU..."
                  />
                </label>
                <span className="pill-group" role="group" aria-label="Filtrar tipo">
                  {ITEM_FILTERS.map((f) => (
                    <button
                      key={f.value}
                      type="button"
                      className="chip-btn"
                      aria-pressed={itemFilter === f.value}
                      onClick={() => setItemFilter(f.value)}
                    >
                      {f.label} ({allItems.filter(f.test).length})
                    </button>
                  ))}
                </span>
                <button
                  type="button"
                  className="chip-btn person-tools__all"
                  aria-pressed={allItemsOpen}
                  onClick={() =>
                    setOpenedIds(allItemsOpen ? new Set() : new Set(shownItems.map((it) => it.id)))
                  }
                >
                  {allItemsOpen ? "Fechar todos" : "Abrir todos"}
                </button>
              </div>

              {shownItems.length === 0 ? (
                <p className="muted">Nenhum item encontrado com esse filtro.</p>
              ) : (
                <div className="person-rows">
                  {shownItems.map((it) => {
                    const isOpen = open.has(it.id);
                    const itemMovs = movements.filter((m) => m.item_id === it.id).slice(0, 8);
                    const marginBarPct = Math.max(4, Math.min(100, Number(it.margin_pct)));
                    return (
                      <article
                        key={it.id}
                        className={`card person-row person-row--long ${isOpen ? "is-open" : ""}`}
                        data-catalog-row={it.id}
                      >
                        <button
                          type="button"
                          className="person-row__head"
                          aria-expanded={isOpen}
                          onClick={() => toggleRow(it.id)}
                        >
                          <span className="person-row__avatar" aria-hidden>
                            {it.kind === "product" ? <Package size={18} /> : <Wrench size={18} />}
                          </span>
                          <span className="person-row__who">
                            <strong title={it.name}>{it.name}</strong>
                            <span className="muted small">
                              {it.kind === "product"
                                ? `Produto · ${formatQty(it.stock_qty)} ${it.unit} em estoque`
                                : `Serviço · por ${UNIT_NAMES[it.unit] ?? it.unit}`}
                            </span>
                            {it.sku && <span className="muted small person-row__code">Cód. {it.sku}</span>}
                          </span>
                          <span className="person-row__progress">
                            <span className="person-row__bar">
                              <Bar
                                pct={marginBarPct}
                                color={it.low_stock ? "var(--warn)" : undefined}
                              />
                            </span>
                            <span className="muted small">
                              {it.low_stock
                                ? `Repor (mín. ${formatQty(it.min_stock)} ${it.unit})`
                                : `Margem ${Number(it.margin_pct).toFixed(1).replace(".", ",")}%`}
                            </span>
                          </span>
                          <span className="person-row__balance">
                            <strong className="tone--ok">{money(it.sale_price)}</strong>
                            <span className="muted small"> / {it.unit}</span>
                          </span>
                          <span className="person-row__chev" aria-hidden>
                            <ChevronDown size={18} />
                          </span>
                        </button>

                        {isOpen && (
                          <div className="person-row__body">
                            <div className="stats">
                              <Stat label="Custo unitário" value={money(it.cost_price)} />
                              <Stat
                                label="Lucro por unidade"
                                value={money(it.unit_margin)}
                                tone={Number(it.unit_margin) >= 0 ? "ok" : "error"}
                              />
                              <Stat
                                label={it.kind === "product" ? "Saldo atual" : "Tipo de item"}
                                value={
                                  it.kind === "product"
                                    ? `${formatQty(it.stock_qty)} ${it.unit}`
                                    : "Serviço sob demanda"
                                }
                                tone={it.low_stock ? "error" : undefined}
                              />
                              <Stat
                                label={it.kind === "product" ? "Saldo mínimo" : "Unidade"}
                                value={
                                  it.kind === "product"
                                    ? `${formatQty(it.min_stock)} ${it.unit}`
                                    : it.unit
                                }
                              />
                            </div>

                            {it.low_stock && (
                              <div className="row">
                                <Badge tone="warn">
                                  Estoque baixo — recomendado fazer nova entrada
                                </Badge>
                              </div>
                            )}

                            {it.notes && <p className="muted small">{it.notes}</p>}

                            {it.kind === "product" && (
                              <details className="details">
                                <summary>Movimentações deste item ({itemMovs.length})</summary>
                                {itemMovs.length === 0 ? (
                                  <p className="muted small">
                                    Nenhuma movimentação manual ou venda lançada ainda.
                                  </p>
                                ) : (
                                  <ul className="items">
                                    {itemMovs.map((m) => (
                                      <li key={m.id} className="item">
                                        <span className="item__main">
                                          <strong className="item__title">
                                            {MOVEMENT_KIND_LABELS[m.kind]} · {formatQty(m.qty)} {it.unit}
                                          </strong>
                                          <span className="item__meta">
                                            {m.reason || "Sem observação"} · {shortDate(m.created_at.slice(0, 10))}
                                          </span>
                                        </span>
                                      </li>
                                    ))}
                                  </ul>
                                )}
                              </details>
                            )}

                            <div className="person-row__actions">
                              <button
                                type="button"
                                className="btn btn--secondary btn--sm"
                                onClick={() => openNewOrder(it)}
                              >
                                <ShoppingBag size={14} /> Vender no pedido
                              </button>
                              {it.kind === "product" && (
                                <button
                                  type="button"
                                  className="btn btn--secondary btn--sm"
                                  onClick={() => setMoveTarget(it)}
                                >
                                  <ArrowDownUp size={14} /> Movimentar estoque
                                </button>
                              )}
                              <button
                                type="button"
                                className="btn btn--secondary btn--sm"
                                onClick={() => openEditItem(it)}
                              >
                                <Pencil size={14} /> Editar
                              </button>
                              <button
                                type="button"
                                className="btn btn--secondary btn--sm"
                                aria-label={`Excluir ${it.name}`}
                                onClick={() => deleteItemWithUndo(it)}
                              >
                                <Trash2 size={14} /> Excluir
                              </button>
                            </div>
                          </div>
                        )}
                      </article>
                    );
                  })}
                </div>
              )}

              {movements.length > 0 && (
                <details className="card details">
                  <summary>Histórico geral de movimentações ({movements.slice(0, 12).length})</summary>
                  <ul className="items">
                    {movements.slice(0, 12).map((m) => (
                      <li key={m.id} className="item">
                        <span className="item__main">
                          <strong className="item__title">{m.item_name}</strong>
                          <span className="item__meta">
                            {MOVEMENT_KIND_LABELS[m.kind]} · {m.reason || "Sem observação"} ·{" "}
                            {shortDate(m.created_at.slice(0, 10))}
                          </span>
                        </span>
                        <span className="item__value">{formatQty(m.qty)}</span>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </>
          )}
        </>
      )}

      {tab === "orders" && (
        <CatalogOrdersTab
          orders={orders}
          search={search}
          onSearchChange={setSearch}
          orderFilter={orderFilter}
          onOrderFilterChange={setOrderFilter}
          open={open}
          onToggleRow={toggleRow}
          onToggleAll={(ids, allOpenNow) => setOpenedIds(allOpenNow ? new Set() : new Set(ids))}
          onOpenNewOrder={() => openNewOrder()}
          onConfirmOrder={openConfirmDialog}
          onCancelOrder={(id) => cancelOrder.mutate(id)}
        />
      )}

      <Sheet
        open={Boolean(confirmTarget)}
        title={`Confirmar Pedido #${confirmTarget ? String(confirmTarget.number).padStart(4, "0") : ""}`}
        onClose={() => setConfirmTarget(null)}
      >
        {confirmTarget && (
          <div className="stack">
            <div className="summary-box">
              <div className="split small">
                <span>Cliente: {confirmTarget.customer_name}</span>
                <strong>{money(confirmTarget.total_amount)}</strong>
              </div>
            </div>
            <label className="check-row">
              <input
                type="checkbox"
                checked={confirmSyncBudget}
                onChange={(e) => setConfirmSyncBudget(e.target.checked)}
              />
              <span>
                Lançar receita no Meu Orçamento{" "}
                <Tip>Desmarque se quiser dar baixa no estoque agora e lançar a entrada depois, quando receber.</Tip>
              </span>
            </label>
            <label className="check-row">
              <input
                type="checkbox"
                checked={confirmSyncCrm}
                onChange={(e) => setConfirmSyncCrm(e.target.checked)}
              />
              <span>Marcar negócio vinculado como Ganho no CRM</span>
            </label>
            <div className="form-actions">
              <Button type="button" variant="secondary" onClick={() => setConfirmTarget(null)}>
                Cancelar
              </Button>
              <Button
                type="button"
                loading={confirmOrder.isPending}
                onClick={() =>
                  confirmOrder.mutate({
                    id: confirmTarget.id,
                    syncBudget: confirmSyncBudget,
                    syncCrm: confirmSyncCrm,
                  })
                }
              >
                Confirmar pedido
              </Button>
            </div>
          </div>
        )}
      </Sheet>

      <CatalogItemSheet
        open={itemOpen}
        editing={editing}
        onClose={() => setItemOpen(false)}
        onSaved={(message) => {
          invalidateAll();
          setFeedbackTone("info");
          setFeedback(message);
        }}
      />

      <StockMoveSheet
        target={moveTarget}
        onClose={() => setMoveTarget(null)}
        onSaved={(message) => {
          invalidateAll();
          setFeedbackTone("info");
          setFeedback(message);
        }}
      />

      <NewOrderSheet
        open={orderOpen}
        presetItem={orderPresetItem}
        allItems={allItems}
        bridges={bridges}
        onClose={() => setOrderOpen(false)}
        onCreated={(order) => {
          invalidateAll();
          setFeedbackTone("info");
          setFeedback(
            order.status === "confirmed"
              ? `Pedido #${String(order.number).padStart(4, "0")} confirmado com baixa de estoque.`
              : `Rascunho do pedido #${String(order.number).padStart(4, "0")} salvo.`,
          );
        }}
      />
    </div>
  );
}
