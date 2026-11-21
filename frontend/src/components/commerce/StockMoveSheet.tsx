import { useEffect, useState, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";

import { errorMessage } from "../../api/client";
import { catalogApi, type CatalogItem, type StockMovementKind } from "../../api/commerce";
import { announce } from "../../lib/announce";
import { formatQty } from "../../lib/commerce";
import { Alert, Button, Sheet } from "../ui";

/** Folha modal para registrar entrada, saída ou ajuste manual de saldo no estoque. */
export function StockMoveSheet({
  target,
  onClose,
  onSaved,
}: {
  target: CatalogItem | null;
  onClose: () => void;
  onSaved: (message: string) => void;
}) {
  const [kind, setKind] = useState<StockMovementKind>("in");
  const [qty, setQty] = useState("1");
  const [reason, setReason] = useState("");
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!target) return;
    setKind("in");
    setQty("1");
    setReason("");
    setErr(null);
  }, [target]);

  const saveMove = useMutation({
    mutationFn: async () => {
      if (!target) return;
      return catalogApi.moveStock(target.id, {
        kind,
        qty: Number(qty.replace(",", ".")),
        reason: reason.trim() || undefined,
      });
    },
    onSuccess: () => {
      onClose();
      onSaved("Movimentação de estoque registrada.");
      announce("Estoque atualizado");
    },
    onError: (e) => setErr(errorMessage(e)),
  });

  const moveNumeric = Number(qty.replace(",", ".")) || 0;
  const currentStock = target ? Number(target.stock_qty) : 0;
  const moveAfterStock = !target
    ? 0
    : kind === "adjust"
      ? Math.max(0, moveNumeric)
      : kind === "in"
        ? currentStock + moveNumeric
        : Math.max(0, currentStock - moveNumeric);

  function submit(e: FormEvent) {
    e.preventDefault();
    saveMove.mutate();
  }

  return (
    <Sheet open={Boolean(target)} title={`Estoque · ${target?.name ?? ""}`} onClose={onClose}>
      <form className="inline-form stack" onSubmit={submit}>
        {err && <Alert tone="error">{err}</Alert>}

        <fieldset className="radios">
          <legend className="field-label">Operação</legend>
          <div className="segmented segmented--3">
            <label>
              <input
                type="radio"
                name="move-kind"
                checked={kind === "in"}
                onChange={() => setKind("in")}
              />
              Entrada (+)
            </label>
            <label>
              <input
                type="radio"
                name="move-kind"
                checked={kind === "out"}
                onChange={() => setKind("out")}
              />
              Saída (−)
            </label>
            <label>
              <input
                type="radio"
                name="move-kind"
                checked={kind === "adjust"}
                onChange={() => setKind("adjust")}
              />
              Ajustar saldo
            </label>
          </div>
        </fieldset>

        <label className="field">
          <span className="field-label">
            {kind === "adjust" ? "Novo saldo final" : "Quantidade"} ({target?.unit ?? "un"})
          </span>
          <input
            type="number"
            min="0"
            step="0.001"
            value={qty}
            onChange={(e) => setQty(e.target.value)}
            required
          />
        </label>

        {target && (
          <div className="summary-box">
            <div className="split small">
              <span>Saldo após movimentação</span>
              <strong>
                {formatQty(target.stock_qty)} → {formatQty(moveAfterStock)} {target.unit}
              </strong>
            </div>
          </div>
        )}

        <label className="field">
          <span className="field-label">Motivo</span>
          <input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Ex.: Compra fornecedor / inventário"
          />
        </label>

        <div className="form-actions">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" loading={saveMove.isPending}>
            Registrar movimentação
          </Button>
        </div>
      </form>
    </Sheet>
  );
}
