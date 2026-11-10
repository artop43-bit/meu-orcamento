import { useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Paperclip, X } from "lucide-react";

import { budgetApi } from "../api/budget";
import { errorMessage } from "../api/client";
import { checkImage, fileUrl } from "../api/support";
import { Tip } from "./help";
import { Alert, Button, Sheet } from "./ui";

export const MAX_RECEIPTS = 3;
const ACCEPT = "image/png,image/jpeg,image/webp";

/**
 * Comprovantes da despesa (foto do recibo, da nota ou do boleto pago). Na despesa já salva,
 * envia e remove na hora; na nova, guarda os arquivos para enviar depois de salvar.
 */
export function ReceiptsField({
  expenseId,
  saved,
  pending,
  setPending,
}: {
  expenseId?: string;
  saved: string[];
  pending: File[];
  setPending: (files: File[]) => void;
}) {
  const queryClient = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [ids, setIds] = useState(saved);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const previews = useMemo(() => pending.map((f) => URL.createObjectURL(f)), [pending]);
  useEffect(() => () => previews.forEach((u) => URL.revokeObjectURL(u)), [previews]);
  const total = ids.length + pending.length;

  async function add(list: FileList | null) {
    if (!list) return;
    setError("");
    const files = Array.from(list);
    const problem = files.map((f) => (f.type === "image/gif" ? `"${f.name}": use PNG, JPG ou WebP.` : checkImage(f))).find(Boolean);
    if (problem) {
      setError(problem);
      return;
    }
    if (total + files.length > MAX_RECEIPTS) {
      setError(`Cada despesa aceita até ${MAX_RECEIPTS} comprovantes.`);
      return;
    }
    if (!expenseId) {
      setPending([...pending, ...files]);
      return;
    }
    setBusy(true);
    try {
      const result = await budgetApi.addReceipts(expenseId, files);
      setIds(result.receipt_ids);
      await queryClient.invalidateQueries({ queryKey: ["budget"] });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    if (!expenseId) return;
    setError("");
    try {
      await budgetApi.removeReceipt(expenseId, id);
      setIds(ids.filter((x) => x !== id));
      await queryClient.invalidateQueries({ queryKey: ["budget"] });
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <div className="receipts">
      <span className="field-label">
        Comprovantes <Tip>Foto do recibo, da nota fiscal ou do boleto pago (até {MAX_RECEIPTS}). Só você vê.</Tip>
      </span>
      <Alert tone="error">{error}</Alert>
      {total > 0 && (
        <ul className="image-picker__list">
          {ids.map((id, i) => (
            <li key={id}>
              <button type="button" className="receipts__thumb" onClick={() => setOpen(id)} aria-label={`Ampliar comprovante ${i + 1}`}>
                <img src={fileUrl(id)} alt={`Comprovante ${i + 1}`} loading="lazy" />
              </button>
              <button type="button" className="icon-btn image-picker__remove" aria-label={`Remover comprovante ${i + 1}`} onClick={() => void remove(id)}>
                <X size={16} />
              </button>
            </li>
          ))}
          {pending.map((file, i) => (
            <li key={`${file.name}-${i}`}>
              <img loading="lazy" decoding="async" src={previews[i]} alt={`Prévia: ${file.name}`} />
              <button type="button" className="icon-btn image-picker__remove" aria-label={`Remover ${file.name}`} onClick={() => setPending(pending.filter((_, j) => j !== i))}>
                <X size={16} />
              </button>
            </li>
          ))}
        </ul>
      )}
      {total < MAX_RECEIPTS && (
        <div>
          <Button type="button" variant="secondary" loading={busy} onClick={() => input.current?.click()}>
            <Paperclip size={16} /> Anexar comprovante
          </Button>
        </div>
      )}
      <input
        ref={input}
        type="file"
        hidden
        multiple
        accept={ACCEPT}
        aria-label="Escolher comprovantes"
        data-testid="receipt-input"
        onChange={(e) => {
          void add(e.target.files);
          e.target.value = "";
        }}
      />
      <Sheet open={open !== null} title="Comprovante" onClose={() => setOpen(null)} wide>
        {open && (
          <div className="lightbox">
            <img loading="lazy" decoding="async" src={fileUrl(open)} alt="Comprovante ampliado" />
            <a className="small" href={fileUrl(open)} target="_blank" rel="noreferrer">
              Abrir em tamanho original
            </a>
          </div>
        )}
      </Sheet>
    </div>
  );
}
