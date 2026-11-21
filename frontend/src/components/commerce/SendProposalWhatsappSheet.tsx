import { useEffect, useState, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";

import { errorMessage } from "../../api/client";
import {
  proposalsApi,
  type CommercialDocument,
  type ProposalBridges,
} from "../../api/commerce";
import { announce } from "../../lib/announce";
import { defaultWhatsappCaption } from "../../lib/commerce";
import { Alert, Button, Sheet } from "../ui";

/** Folha modal para enviar um documento PDF diretamente em uma conversa da Mensageria. */
export function SendProposalWhatsappSheet({
  target,
  bridges,
  onClose,
  onSent,
}: {
  target: CommercialDocument | null;
  bridges: ProposalBridges | undefined;
  onClose: () => void;
  onSent: () => void;
}) {
  const [chatId, setChatId] = useState("");
  const [caption, setCaption] = useState("");
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!target) return;
    setCaption(defaultWhatsappCaption(target));
    const linked = bridges?.contacts.find((c) => c.id === target.contact_id)?.messaging_chat_id;
    setChatId(linked ?? "");
    setErr(null);
  }, [target, bridges]);

  const sendWhatsapp = useMutation({
    mutationFn: () =>
      proposalsApi.sendToMessaging(target!.id, {
        chat_id: chatId,
        caption: caption.trim() || undefined,
      }),
    onSuccess: () => {
      onClose();
      onSent();
      announce("PDF enviado para a Mensageria");
    },
    onError: (e) => setErr(errorMessage(e)),
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!chatId) {
      setErr("Escolha uma conversa da Mensageria.");
      return;
    }
    sendWhatsapp.mutate();
  }

  return (
    <Sheet
      open={Boolean(target)}
      title={`Enviar PDF no WhatsApp · ${target?.title ?? ""}`}
      onClose={onClose}
    >
      <form className="inline-form stack" onSubmit={submit}>
        {err && <Alert tone="error">{err}</Alert>}

        <label className="field">
          <span className="field-label">Conversa da Mensageria</span>
          <select value={chatId} onChange={(e) => setChatId(e.target.value)} required>
            <option value="">Escolha o contato do WhatsApp...</option>
            {(bridges?.chats ?? []).map((chat) => (
              <option key={chat.id} value={chat.id}>
                {chat.name} {chat.phone_display ? `(${chat.phone_display})` : ""}
              </option>
            ))}
          </select>
        </label>

        <div className="field">
          <label htmlFor="prop-wa-caption" className="field-label">
            Mensagem que acompanha o PDF
          </label>
          <textarea
            id="prop-wa-caption"
            className="charge__text"
            rows={4}
            value={caption}
            onChange={(e) => setCaption(e.target.value)}
          />
        </div>

        <div className="form-actions">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" loading={sendWhatsapp.isPending}>
            Enviar PDF agora
          </Button>
        </div>
      </form>
    </Sheet>
  );
}
