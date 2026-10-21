import { useRef, useState } from "react";
import { Camera } from "lucide-react";

import { budgetApi, type ReceiptReading } from "../api/budget";
import { errorMessage } from "../api/client";
import { Button } from "./ui";

/**
 * "Ler comprovante": foto do cupom, da nota ou do boleto preenche valor, data e descrição.
 * A leitura é feita no servidor do app (sem serviço externo) e só preenche o formulário:
 * a pessoa confere e salva. A foto fica anexada à despesa.
 */
export function ReceiptReader({ onRead }: { onRead: (reading: ReceiptReading, file: File) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function pick(file: File | undefined) {
    if (!file) return;
    setError("");
    setBusy(true);
    try {
      onRead(await budgetApi.readReceipt(file), file);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }

  return (
    <div className="receipt-reader">
      <Button type="button" variant="secondary" loading={busy} onClick={() => input.current?.click()}>
        <Camera size={16} aria-hidden /> {busy ? "Lendo o comprovante…" : "Ler comprovante (foto)"}
      </Button>
      <input
        ref={input}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        className="sr-only"
        tabIndex={-1}
        aria-label="Foto do comprovante para leitura"
        data-testid="receipt-reader-input"
        onChange={(e) => void pick(e.target.files?.[0])}
      />
      {error && (
        <p className="tone--error small" role="alert" style={{ margin: 0 }}>
          {error}
        </p>
      )}
    </div>
  );
}
