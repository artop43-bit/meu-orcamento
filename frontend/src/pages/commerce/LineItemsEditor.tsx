import { useEffect, useId, useState } from "react";
import { Plus, Trash2 } from "lucide-react";

import type { CatalogItem, LineItemDraft } from "../../api/commerce";
import { MoneyInput } from "../../components/budget";
import { roundHalfUp } from "../../lib/commerce";
import { money, moneyInput, parseMoney } from "../../lib/format";

function UnitPriceInput({
  value,
  onCommit,
}: {
  value: number | string;
  onCommit: (next: number) => void;
}) {
  const numVal = Number(value) || 0;
  const [text, setText] = useState(() => (numVal > 0 ? moneyInput(String(numVal)) : ""));

  useEffect(() => {
    const currentParsed = Number(parseMoney(text) ?? 0);
    if (Math.abs(currentParsed - numVal) > 0.005) {
      setText(numVal > 0 ? moneyInput(String(numVal)) : "");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [numVal]);

  return (
    <MoneyInput
      value={text}
      placeholder="0,00"
      required={false}
      onChange={(raw) => {
        setText(raw);
        const parsed = parseMoney(raw);
        if (parsed !== null) {
          onCommit(Number(parsed));
        } else if (!raw.trim()) {
          onCommit(0);
        }
      }}
    />
  );
}

/** Editor de linhas (itens do catálogo ou livres) para Pedidos e Documentos em PDF. */
export function LineItemsEditor({
  label,
  addLabel,
  customOptionLabel,
  lines,
  catalogItems,
  onChange,
}: {
  label: string;
  addLabel: string;
  customOptionLabel: string;
  lines: LineItemDraft[];
  catalogItems: CatalogItem[];
  onChange: (next: LineItemDraft[]) => void;
}) {
  const editorId = useId();

  function updateLine(idx: number, patch: Partial<LineItemDraft>) {
    onChange(
      lines.map((row, i) => {
        if (i !== idx) return row;
        if (patch.item_id !== undefined) {
          const found = catalogItems.find((it) => it.id === patch.item_id);
          if (found) {
            return {
              ...row,
              item_id: found.id,
              kind: found.kind,
              name: found.name,
              unit: found.unit,
              unit_price: found.sale_price,
            };
          }
          return { ...row, item_id: null };
        }
        return { ...row, ...patch };
      }),
    );
  }

  return (
    <div className="stack">
      <div className="split">
        <span className="field-label">{label}</span>
        <button
          type="button"
          className="btn btn--secondary btn--sm"
          onClick={() => onChange([...lines, { name: "", unit: "un", qty: 1, unit_price: 0 }])}
        >
          <Plus size={14} /> {addLabel}
        </button>
      </div>
      <div className="line-items-stack">
        {lines.map((line, idx) => {
          const rowTotal = roundHalfUp((Number(line.qty) || 0) * (Number(line.unit_price) || 0));
          const catalogId = `${editorId}-catalog-${idx}`;
          const descriptionId = `${editorId}-description-${idx}`;
          return (
            <div key={idx} className="line-item-card">
              <div className="line-item-card__top">
                <div className="field">
                  <label className="small muted" htmlFor={catalogId}>Catálogo</label>
                  <select
                    id={catalogId}
                    value={line.item_id ?? ""}
                    onChange={(e) => updateLine(idx, { item_id: e.target.value || null })}
                  >
                    <option value="">{customOptionLabel}</option>
                    {catalogItems.map((it) => (
                      <option key={it.id} value={it.id}>
                        {it.name} ({money(it.sale_price)})
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field line-item-card__description">
                  <label className="small muted" htmlFor={descriptionId}>Descrição</label>
                  <textarea
                    id={descriptionId}
                    rows={3}
                    value={line.name}
                    onChange={(e) => updateLine(idx, { name: e.target.value })}
                    placeholder="Descrição do item"
                  />
                </div>
              </div>
              <div className="line-item-card__nums">
                <label className="field">
                  <span className="small muted">Qtd</span>
                  <input
                    type="number"
                    min="0.001"
                    step="0.001"
                    value={line.qty}
                    onChange={(e) => updateLine(idx, { qty: Number(e.target.value) || 0 })}
                  />
                </label>
                <label className="field">
                  <span className="small muted">Unitário (R$)</span>
                  <UnitPriceInput
                    value={line.unit_price}
                    onCommit={(next) => updateLine(idx, { unit_price: next })}
                  />
                </label>
                <div className="line-item-card__sub">
                  <span className="small muted">Subtotal: </span>
                  <strong>{money(rowTotal)}</strong>
                </div>
                <button
                  type="button"
                  className="icon-btn icon-btn--bordered"
                  aria-label="Remover linha"
                  onClick={() => onChange(lines.filter((_, i) => i !== idx))}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
