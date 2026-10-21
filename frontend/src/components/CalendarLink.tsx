import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy } from "lucide-react";

import { api, errorMessage } from "../api/client";
import { announce } from "../lib/announce";
import { Alert, Button } from "./ui";

const KEY = ["calendar-link"] as const;

/**
 * Calendário › Vencimentos na agenda (v1.4): link secreto que o Google Agenda e o iPhone
 * assinam. Trocar o link desliga o anterior; desligar apaga o acesso.
 */
export function CalendarLink() {
  const queryClient = useQueryClient();
  const link = useQuery({ queryKey: KEY, queryFn: () => api.get<{ url: string | null }>("/calendar-link") });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const url = link.data?.url ?? null;

  async function run(fn: () => Promise<unknown>, message: string) {
    setBusy(true);
    setError("");
    try {
      await fn();
      await queryClient.invalidateQueries({ queryKey: KEY });
      announce(message);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function copy() {
    if (!url) return;
    await navigator.clipboard.writeText(url).catch(() => undefined);
    announce("Link copiado");
  }

  return (
    <div className="stack">
      <Alert tone="error">{error}</Alert>
      <p style={{ margin: 0 }}>
        Contas a pagar, faturas do cartão e despesas previstas aparecem na agenda do celular, junto dos seus compromissos. A agenda busca as
        novidades sozinha de tempos em tempos.
      </p>
      {!url ? (
        <div>
          <Button type="button" loading={busy} onClick={() => void run(() => api.post("/calendar-link"), "Link da agenda criado")}>
            Criar link da agenda
          </Button>
        </div>
      ) : (
        <>
          <label>
            Link da agenda
            <input readOnly value={url} onFocus={(e) => e.currentTarget.select()} />
          </label>
          <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
            <Button type="button" onClick={() => void copy()}>
              <Copy size={16} aria-hidden /> Copiar link
            </Button>
            <a className="btn btn--secondary" href={url.replace(/^https?:/, "webcal:")}>
              Abrir no iPhone ou Mac
            </a>
          </div>
          <ul className="muted small calendar-link__steps">
            <li>
              <strong>Google Agenda (no computador):</strong> Outras agendas › + › Do URL › cole o link.
            </li>
            <li>
              <strong>iPhone:</strong> toque em “Abrir no iPhone ou Mac” e confirme a assinatura.
            </li>
          </ul>
          <p className="muted small" style={{ margin: 0 }}>
            Quem tem o link vê os vencimentos. Se ele vazar, troque: o anterior para de funcionar na hora.
          </p>
          <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
            <Button type="button" variant="secondary" loading={busy} onClick={() => void run(() => api.post("/calendar-link"), "Link da agenda trocado")}>
              Trocar o link
            </Button>
            <Button type="button" variant="secondary" disabled={busy} onClick={() => void run(() => api.delete("/calendar-link"), "Link da agenda desligado")}>
              Desligar
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
