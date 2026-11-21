import { useEffect, useRef, useState, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";

import { errorMessage } from "../../api/client";
import {
  catalogApi,
  type CatalogBridges,
  type CatalogItem,
  type CommercialOrder,
  type LineItemDraft,
} from "../../api/commerce";
import { announce } from "../../lib/announce";
import { calcDraftTotals } from "../../lib/commerce";
import { money, moneyToNumber } from "../../lib/format";
import { LineItemsEditor } from "../../pages/commerce/LineItemsEditor";
import { MoneyInput } from "../budget";
import { Tip } from "../help";
import { Alert, Button, Sheet } from "../ui";

/** Folha modal para registrar um novo pedido de venda integrado ao estoque, CRM e Orçamento. */
export function NewOrderSheet({
  open,
  presetItem,
  allItems,
  bridges,
  onClose,
  onCreated,
}: {
  open: boolean;
  presetItem?: CatalogItem;
  allItems: CatalogItem[];
  bridges: CatalogBridges | undefined;
  onClose: () => void;
  onCreated: (order: CommercialOrder) => void;
}) {
  const [orderContactId, setOrderContactId] = useState("");
  const [orderCustomerName, setOrderCustomerName] = useState("");
  const [orderLines, setOrderLines] = useState<LineItemDraft[]>([]);
  const [orderDiscount, setOrderDiscount] = useState("");
  const [orderNotes, setOrderNotes] = useState("");
  const [confirmNow, setConfirmNow] = useState(true);
  const [syncBudget, setSyncBudget] = useState(true);
  const [syncCrm, setSyncCrm] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const wasOpen = useRef(false);

  useEffect(() => {
    const opening = open && !wasOpen.current;
    wasOpen.current = open;
    if (!opening) return;
    const picked = presetItem ?? allItems.find((i) => i.active);
    setOrderContactId("");
    setOrderCustomerName("");
    setOrderLines(
      picked
        ? [
            {
              item_id: picked.id,
              kind: picked.kind,
              name: picked.name,
              unit: picked.unit,
              qty: 1,
              unit_price: picked.sale_price,
            },
          ]
        : [{ name: "", unit: "un", qty: 1, unit_price: 0 }],
    );
    setOrderDiscount("");
    setOrderNotes("");
    setConfirmNow(true);
    setSyncBudget(true);
    setSyncCrm(true);
    setErr(null);
  }, [open, presetItem, allItems]);

  const createOrder = useMutation({
    mutationFn: () =>
      catalogApi.createOrder({
        contact_id: orderContactId || null,
        customer_name: orderCustomerName.trim() || undefined,
        items: orderLines,
        discount: moneyToNumber(orderDiscount),
        notes: orderNotes.trim() || undefined,
        confirm_now: confirmNow,
        sync_budget: confirmNow && syncBudget,
        sync_crm: confirmNow && syncCrm,
      }),
    onSuccess: (order) => {
      onClose();
      onCreated(order);
      announce("Pedido salvo");
    },
    onError: (e) => setErr(errorMessage(e)),
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!orderContactId && !orderCustomerName.trim()) {
      setErr("Escolha um contato do CRM ou informe o nome do cliente.");
      return;
    }
    if (orderLines.length === 0) {
      setErr("Adicione pelo menos um item ao pedido.");
      return;
    }
    createOrder.mutate();
  }

  const draftTotals = calcDraftTotals(orderLines, moneyToNumber(orderDiscount));

  return (
    <Sheet open={open} title="Novo pedido integrado" onClose={onClose}>
      <form className="inline-form stack" onSubmit={submit}>
        {err && <Alert tone="error">{err}</Alert>}

        <div className="grid-2">
          <label className="field">
            <span className="field-label">Contato do CRM (opcional)</span>
            <select
              value={orderContactId}
              onChange={(e) => {
                const id = e.target.value;
                setOrderContactId(id);
                const c = bridges?.contacts.find((item) => item.id === id);
                if (c && !orderCustomerName) setOrderCustomerName(c.name);
              }}
            >
              <option value="">Informar nome manual</option>
              {(bridges?.contacts ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} {c.phone_display ? `(${c.phone_display})` : ""}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field-label">Nome do cliente</span>
            <input
              value={orderCustomerName}
              onChange={(e) => setOrderCustomerName(e.target.value)}
              placeholder="Nome ou empresa"
            />
          </label>
        </div>

        <LineItemsEditor
          label="Itens do pedido"
          addLabel="Adicionar linha"
          customOptionLabel="Item personalizado"
          lines={orderLines}
          catalogItems={allItems}
          onChange={setOrderLines}
        />

        <div className="grid-2">
          <label className="field">
            <span className="field-label">Desconto (R$)</span>
            <MoneyInput value={orderDiscount} onChange={setOrderDiscount} placeholder="0,00" required={false} />
          </label>
          <div className="summary-box">
            <div className="split small">
              <span>Subtotal</span>
              <span>{money(draftTotals.subtotal)}</span>
            </div>
            <div className="split">
              <strong>Total do pedido</strong>
              <strong className="tone--ok">{money(draftTotals.total)}</strong>
            </div>
          </div>
        </div>

        <div className="stack stack--tight">
          <label className="check-row">
            <input type="checkbox" checked={confirmNow} onChange={(e) => setConfirmNow(e.target.checked)} />
            <span>
              Confirmar pedido e baixar estoque agora{" "}
              <Tip>Desmarque se quiser salvar como rascunho para confirmar depois.</Tip>
            </span>
          </label>
          {confirmNow && (
            <>
              <label className="check-row">
                <input type="checkbox" checked={syncBudget} onChange={(e) => setSyncBudget(e.target.checked)} />
                <span>Lançar automaticamente como receita no Meu Orçamento</span>
              </label>
              <label className="check-row">
                <input type="checkbox" checked={syncCrm} onChange={(e) => setSyncCrm(e.target.checked)} />
                <span>Criar negócio ganho no Funil CRM</span>
              </label>
            </>
          )}
        </div>

        <div className="field">
          <label htmlFor="cat-order-notes" className="field-label">
            Observações do pedido (opcional)
          </label>
          <textarea
            id="cat-order-notes"
            rows={2}
            value={orderNotes}
            onChange={(e) => setOrderNotes(e.target.value)}
          />
        </div>

        <div className="form-actions">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" loading={createOrder.isPending}>
            {confirmNow ? "Confirmar e salvar pedido" : "Salvar rascunho"}
          </Button>
        </div>
      </form>
    </Sheet>
  );
}
