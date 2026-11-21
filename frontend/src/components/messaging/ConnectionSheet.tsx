import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { QrCode, RefreshCw, Unplug } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";

import { errorMessage } from "../../api/client";
import { messagingApi, messagingKeys, type MessagingSession } from "../../api/messaging";
import { announce } from "../../lib/announce";
import { connectButtonLabel, sessionBadgeTone, sessionStatusLabel } from "../../lib/messaging";
import { LoadingRegion, Sheet, Skeleton } from "../ui";

const QR_SIZE = 212;

/**
 * Janela de conexão com o WhatsApp (aparelho conectado): gera o QR Code, mostra o número
 * conectado e permite desconectar.
 */
export function ConnectionSheet({
  open,
  onClose,
  session,
  loadError,
}: {
  open: boolean;
  onClose: () => void;
  session: MessagingSession | undefined;
  loadError: unknown;
}) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [confirmDisconnect, setConfirmDisconnect] = useState(false);
  const status = session?.status ?? "disconnected";
  const previousStatus = useRef(status);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setConfirmDisconnect(false);
  }, [open]);

  // Avisa o leitor de tela quando o pareamento termina com a janela aberta.
  useEffect(() => {
    if (open && status === "ready" && previousStatus.current !== "ready") announce("WhatsApp conectado.");
    previousStatus.current = status;
  }, [open, status]);

  const connect = useMutation({
    mutationFn: messagingApi.connect,
    onSuccess: (res) => {
      setError(null);
      queryClient.setQueryData(messagingKeys.session, res);
      announce(res.status === "error" ? (res.last_error ?? "Não foi possível conectar.") : "Preparando a conexão.");
    },
    onError: (err) => setError(errorMessage(err)),
  });

  const disconnect = useMutation({
    mutationFn: messagingApi.disconnect,
    onSuccess: (res) => {
      setError(null);
      setConfirmDisconnect(false);
      queryClient.setQueryData(messagingKeys.session, res);
      announce("WhatsApp desconectado.");
    },
    onError: (err) => setError(errorMessage(err)),
  });

  const busy = connect.isPending || disconnect.isPending;
  const statusText = sessionStatusLabel(status);

  function connectButton(label = connectButtonLabel(status, session?.last_error)) {
    return (
      <button type="button" className="btn btn--primary" onClick={() => connect.mutate()} disabled={busy}>
        {status === "error" ? <RefreshCw size={16} aria-hidden /> : <QrCode size={16} aria-hidden />}
        {connect.isPending ? "Aguarde…" : label}
      </button>
    );
  }

  function cancelButton() {
    return (
      <button type="button" className="btn btn--secondary" onClick={() => disconnect.mutate()} disabled={busy}>
        Cancelar
      </button>
    );
  }

  function disconnectFlow() {
    if (!confirmDisconnect) {
      return (
        <button type="button" className="btn btn--secondary" onClick={() => setConfirmDisconnect(true)} disabled={busy}>
          <Unplug size={16} aria-hidden />
          Desconectar
        </button>
      );
    }
    return (
      <div className="stack stack--tight">
        <p className="small m-0">
          Isso desconecta o WhatsApp deste site e apaga a sessão salva.
        </p>
        <div className="row">
          <button
            type="button"
            className="btn btn--secondary"
            onClick={() => setConfirmDisconnect(false)}
            disabled={disconnect.isPending}
          >
            Voltar
          </button>
          <button type="button" className="btn btn--danger" onClick={() => disconnect.mutate()} disabled={busy}>
            <Unplug size={16} aria-hidden />
            {disconnect.isPending ? "Desconectando…" : "Desconectar"}
          </button>
        </div>
      </div>
    );
  }

  function preparing(text: string) {
    return (
      <div className="wa-qr">
        <p className="small muted m-0">
          {text}
        </p>
        <LoadingRegion label={text}>
          <Skeleton width={`${QR_SIZE}px`} height={QR_SIZE} radius={8} />
        </LoadingRegion>
      </div>
    );
  }

  function body() {
    if (!session) {
      if (loadError) {
        return (
          <p className="alert alert--error m-0" role="alert">
            {errorMessage(loadError)}
          </p>
        );
      }
      return <p className="muted small">Carregando…</p>;
    }

    if (!session.available) {
      return (
        <p className="alert alert--info m-0" role="status">
          A conexão com o WhatsApp não está disponível neste servidor.
        </p>
      );
    }

    switch (status) {
      case "connecting":
        return (
          <>
            {preparing("Preparando a conexão…")}
            <div className="row">
              {cancelButton()}
            </div>
          </>
        );
      case "qr":
        return (
          <>
            {session.qr_code ? (
              <div className="wa-qr">
                <p className="small m-0">
                  No celular, abra o WhatsApp › Configurações (ou ⋮) › Aparelhos conectados › Conectar um aparelho e
                  aponte para este código.
                </p>
                <div className="wa-qr__box">
                  <QRCodeSVG value={session.qr_code} size={QR_SIZE} title="QR Code para conectar o WhatsApp" />
                </div>
                <p className="small muted m-0">
                  O código se renova sozinho.
                </p>
              </div>
            ) : (
              preparing("Preparando a conexão…")
            )}
            <div className="row">
              {cancelButton()}
            </div>
          </>
        );
      case "ready":
        return (
          <>
            {session.pending_outbox > 0 && (
              <p className="small muted m-0">
                {session.pending_outbox === 1
                  ? "1 mensagem na fila de envio."
                  : `${session.pending_outbox} mensagens na fila de envio.`}
              </p>
            )}
            {disconnectFlow()}
          </>
        );
      case "error":
        return (
          <>
            <p className="alert alert--error m-0" role="alert">
              {session.last_error || "A conexão com o WhatsApp deu erro."}
            </p>
            <div className="row">
              {connectButton()}
              {!confirmDisconnect && disconnectFlow()}
            </div>
            {confirmDisconnect && disconnectFlow()}
          </>
        );
      default:
        return (
          <>
            <p className="small m-0">
              Conecte o seu WhatsApp para conversar por aqui. Você vai ler um QR Code com o celular, como no
              WhatsApp Web.
            </p>
            {session.last_error && (
              <p className="alert alert--error m-0" role="alert">
                {session.last_error}
              </p>
            )}
            <div className="row">
              {connectButton()}
            </div>
          </>
        );
    }
  }

  return (
    <Sheet open={open} title="Conexão com o WhatsApp" onClose={onClose}>
      <div className="stack">
        <div className="wa-conn-summary">
          <div className="row row--between">
            <strong>Status da conexão</strong>
            <span className={`badge ${sessionBadgeTone(status)}`}>{statusText}</span>
          </div>
          {session?.available && status === "ready" && (
            <dl className="wa-conn-meta">
              <div>
                <dt className="muted small">Número</dt>
                <dd>{session.phone_display || "—"}</dd>
              </div>
              <div>
                <dt className="muted small">Nome</dt>
                <dd>{session.display_name || "—"}</dd>
              </div>
            </dl>
          )}
        </div>
        {body()}
        {error && (
          <p className="alert alert--error m-0" role="alert">
            {error}
          </p>
        )}
      </div>
    </Sheet>
  );
}
