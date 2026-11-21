import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Copy, MessageCircle } from "lucide-react";

import { errorMessage } from "../../api/client";
import { agendaApi, type AgendaTimelineItem } from "../../api/work";
import { announce } from "../../lib/announce";
import { Alert, Button, Sheet } from "../ui";

/** Folha modal para revisar, copiar ou enviar a confirmação de compromisso pelo WhatsApp. */
export function WhatsappConfirmSheet({
  item,
  initialText,
  chatName,
  hasChat,
  onClose,
  onSent,
}: {
  item: AgendaTimelineItem | null;
  initialText: string;
  chatName: string | null;
  hasChat: boolean;
  onClose: () => void;
  onSent: () => void;
}) {
  const [text, setText] = useState(initialText);
  const [copied, setCopied] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setText(initialText);
    setCopied(false);
    setErr(null);
  }, [initialText, item]);

  const sendWhatsappNow = useMutation({
    mutationFn: () =>
      agendaApi.confirmWhatsapp(item!.id, {
        send_now: true,
        custom_text: text.trim(),
      }),
    onSuccess: () => {
      onClose();
      onSent();
      announce("Confirmação enviada");
    },
    onError: (e) => setErr(errorMessage(e)),
  });

  async function copyConfirmation() {
    if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    }
  }

  return (
    <Sheet
      open={Boolean(item)}
      title={`Confirmar no WhatsApp · ${item?.title ?? ""}`}
      onClose={onClose}
    >
      <div className="stack">
        {err && <Alert tone="error">{err}</Alert>}
        <p className="muted small">
          {hasChat
            ? `Conversa vinculada: ${chatName || "Contato WhatsApp"}.`
            : "Nenhuma conversa vinculada ainda — você pode copiar a mensagem abaixo e enviar manualmente."}
        </p>
        <div className="field">
          <label htmlFor="agenda-wa-text" className="field-label">
            Texto da confirmação
          </label>
          <textarea
            id="agenda-wa-text"
            className="charge__text"
            rows={4}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
        </div>
        <div className="form-actions">
          <Button type="button" variant="secondary" onClick={copyConfirmation}>
            <Copy size={14} /> {copied ? "Copiado!" : "Copiar texto"}
          </Button>
          {hasChat && (
            <Button
              type="button"
              loading={sendWhatsappNow.isPending}
              onClick={() => sendWhatsappNow.mutate()}
            >
              <MessageCircle size={14} /> Enviar na Mensageria
            </Button>
          )}
        </div>
      </div>
    </Sheet>
  );
}
