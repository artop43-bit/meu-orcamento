import { useEffect, useState, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";

import { errorMessage } from "../../api/client";
import { catalogApi, type CatalogItem, type CatalogItemKind } from "../../api/commerce";
import { announce } from "../../lib/announce";
import { money, moneyInput, moneyToNumber } from "../../lib/format";
import { MoneyInput } from "../budget";
import { Tip } from "../help";
import { Alert, Button, Sheet } from "../ui";

/** Folha modal para cadastrar ou editar produto (com estoque) ou serviço do catálogo. */
export function CatalogItemSheet({
  open,
  editing,
  onClose,
  onSaved,
}: {
  open: boolean;
  editing: CatalogItem | null;
  onClose: () => void;
  onSaved: (message: string) => void;
}) {
  const [itemKind, setItemKind] = useState<CatalogItemKind>("product");
  const [sku, setSku] = useState("");
  const [name, setName] = useState("");
  const [unit, setUnit] = useState("un");
  const [costPrice, setCostPrice] = useState("");
  const [salePrice, setSalePrice] = useState("");
  const [stockQty, setStockQty] = useState("0");
  const [minStock, setMinStock] = useState("0");
  const [notes, setNotes] = useState("");
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    if (editing) {
      setItemKind(editing.kind);
      setSku(editing.sku || "");
      setName(editing.name);
      setUnit(editing.unit);
      setCostPrice(Number(editing.cost_price) > 0 ? moneyInput(String(editing.cost_price)) : "0,00");
      setSalePrice(Number(editing.sale_price) > 0 ? moneyInput(String(editing.sale_price)) : "");
      setStockQty(String(editing.stock_qty));
      setMinStock(String(editing.min_stock));
      setNotes(editing.notes || "");
    } else {
      setItemKind("product");
      setSku("");
      setName("");
      setUnit("un");
      setCostPrice("0,00");
      setSalePrice("");
      setStockQty("0");
      setMinStock("0");
      setNotes("");
    }
    setErr(null);
  }, [open, editing]);

  const saveItem = useMutation({
    mutationFn: async () => {
      const numCost = moneyToNumber(costPrice);
      const numSale = moneyToNumber(salePrice);
      const numStock = Number(stockQty.replace(",", ".")) || 0;
      const numMin = Number(minStock.replace(",", ".")) || 0;
      if (editing) {
        return catalogApi.updateItem(editing.id, {
          kind: itemKind,
          sku: sku.trim() || undefined,
          name: name.trim(),
          unit: unit.trim() || "un",
          cost_price: numCost,
          sale_price: numSale,
          min_stock: numMin,
          notes: notes.trim() || undefined,
        });
      }
      return catalogApi.createItem({
        kind: itemKind,
        sku: sku.trim() || undefined,
        name: name.trim(),
        unit: unit.trim() || "un",
        cost_price: numCost,
        sale_price: numSale,
        stock_qty: numStock,
        min_stock: numMin,
        notes: notes.trim() || undefined,
      });
    },
    onSuccess: () => {
      onClose();
      onSaved(editing ? "Item atualizado no catálogo." : "Item cadastrado no catálogo.");
      announce("Catálogo atualizado");
    },
    onError: (e) => setErr(errorMessage(e)),
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) {
      setErr("Informe o nome do produto ou serviço.");
      return;
    }
    saveItem.mutate();
  }

  const previewCost = moneyToNumber(costPrice);
  const previewSale = moneyToNumber(salePrice);
  const previewProfit = Math.round((previewSale - previewCost) * 100) / 100;
  const previewMargin = previewSale > 0 ? Math.round((previewProfit / previewSale) * 1000) / 10 : 0;

  return (
    <Sheet
      open={open}
      title={editing ? "Editar item do catálogo" : "Novo item do catálogo"}
      onClose={onClose}
    >
      <form className="inline-form stack" onSubmit={submit}>
        {err && <Alert tone="error">{err}</Alert>}

        <fieldset className="radios">
          <legend className="field-label">Tipo</legend>
          <div className="segmented">
            <label>
              <input
                type="radio"
                name="catalog-item-kind"
                checked={itemKind === "product"}
                onChange={() => setItemKind("product")}
              />
              Produto com estoque
            </label>
            <label>
              <input
                type="radio"
                name="catalog-item-kind"
                checked={itemKind === "service"}
                onChange={() => setItemKind("service")}
              />
              Serviço
            </label>
          </div>
        </fieldset>

        <div className="grid-2">
          <label className="field">
            <span className="field-label">Nome</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              placeholder="Ex.: Instalação solar"
            />
          </label>
          <label className="field">
            <span className="field-label">Código / SKU (opcional)</span>
            <input value={sku} onChange={(e) => setSku(e.target.value)} placeholder="Ex.: LED-50W" />
          </label>
        </div>

        <div className="grid-2">
          <label className="field">
            <span className="field-label">Custo unitário (R$)</span>
            <MoneyInput value={costPrice} onChange={setCostPrice} placeholder="0,00" required={false} />
          </label>
          <label className="field">
            <span className="field-label">Preço de venda (R$)</span>
            <MoneyInput value={salePrice} onChange={setSalePrice} placeholder="0,00" required />
          </label>
        </div>

        <div className="grid-2">
          <label className="field">
            <span className="field-label">Unidade</span>
            <input value={unit} onChange={(e) => setUnit(e.target.value)} placeholder="un, h, kg" />
          </label>
          {itemKind === "product" && (
            <label className="field">
              <span className="field-label">
                Estoque mínimo{" "}
                <Tip>Quando o saldo chegar a esse valor ou abaixo, o catálogo avisa na tela para repor.</Tip>
              </span>
              <input
                type="number"
                step="0.001"
                value={minStock}
                onChange={(e) => setMinStock(e.target.value)}
              />
            </label>
          )}
        </div>

        {!editing && itemKind === "product" && (
          <label className="field">
            <span className="field-label">Estoque inicial</span>
            <input
              type="number"
              step="0.001"
              value={stockQty}
              onChange={(e) => setStockQty(e.target.value)}
            />
          </label>
        )}

        <div className="summary-box">
          <div className="split small">
            <span>Lucro unitário previsto</span>
            <strong className={previewProfit >= 0 ? "tone--ok" : "tone--error"}>
              {money(previewProfit)} ({previewMargin.toFixed(1).replace(".", ",")}%)
            </strong>
          </div>
        </div>

        <div className="field">
          <label htmlFor="cat-item-notes" className="field-label">
            Observações (opcional)
          </label>
          <textarea
            id="cat-item-notes"
            rows={2}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </div>

        <div className="form-actions">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" loading={saveItem.isPending}>
            {editing ? "Salvar alterações" : "Cadastrar item"}
          </Button>
        </div>
      </form>
    </Sheet>
  );
}
