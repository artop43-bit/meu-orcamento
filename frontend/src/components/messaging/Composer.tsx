import {
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type ClipboardEvent,
  type DragEvent,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import {
  FileText,
  Mic,
  Paperclip,
  SendHorizontal,
  Square,
  WifiOff,
  X,
  Zap,
} from "lucide-react";

import { errorMessage } from "../../api/client";
import {
  useBudgetContext,
  useMessagingSession,
  useQuickReplies,
  useSendMedia,
  useSendMessage,
  type MessagingMessage,
  type QuickReply,
} from "../../api/messaging";
import {
  expandQuickReply,
  formatBytes,
  MAX_MEDIA_BYTES,
  shortenPreview,
  snapshotFile,
} from "../../lib/messaging";
import { money } from "../../lib/format";
import { useMessagingOutlet } from "./context";
import { QuickReplyMenu } from "./QuickReplyMenu";

/**
 * Campo de mensagem da conversa aberta: texto, anexo (foto/áudio/vídeo/documento até 8 MB),
 * colar mídia (Ctrl+V), arrastar e soltar, gravação de áudio e respostas rápidas com `/`.
 */
export function Composer({
  chatId,
  chatName,
  chatPhone,
  replyTo,
  onCancelReply,
  droppedFile,
  externalDraft,
}: {
  chatId: string;
  chatName?: string | null;
  chatPhone?: string | null;
  replyTo: MessagingMessage | null;
  onCancelReply: () => void;
  droppedFile?: { file: File; seq: number } | null;
  externalDraft?: { text: string; seq: number } | null;
}) {
  const { openConnection } = useMessagingOutlet();
  const session = useMessagingSession(false).data;
  const budgetCtx = useBudgetContext(chatId).data;
  const quickReplies = useQuickReplies().data ?? [];
  const sendMutation = useSendMessage(chatId);
  const sendMediaMutation = useSendMedia(chatId);
  const [draft, setDraft] = useState("");
  const [attachment, setAttachment] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewBroken, setPreviewBroken] = useState(false);
  const [recording, setRecording] = useState(false);
  const [recSeconds, setRecSeconds] = useState(0);
  const [sendError, setSendError] = useState<string | null>(null);
  const [quickOpen, setQuickOpen] = useState(false);

  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const recTimerRef = useRef<number | null>(null);

  // Só bloqueia quando o status é conhecido; se o status não carregou, o servidor decide (409).
  const blocked = session !== undefined && !session.connected;
  const sending = sendMutation.isPending || sendMediaMutation.isPending;
  const canRecord =
    typeof window !== "undefined" &&
    typeof MediaRecorder !== "undefined" &&
    Boolean(navigator.mediaDevices?.getUserMedia);

  useEffect(() => {
    if (replyTo) inputRef.current?.focus();
  }, [replyTo]);

  useEffect(() => {
    if (blocked) setSendError(null);
  }, [blocked]);

  useEffect(() => {
    if (externalDraft && externalDraft.seq > 0) {
      setDraft(externalDraft.text);
      window.setTimeout(() => inputRef.current?.focus(), 30);
    }
  }, [externalDraft]);

  useEffect(() => {
    if (droppedFile && droppedFile.seq > 0) {
      void attachFile(droppedFile.file);
    }
  }, [droppedFile]);

  useEffect(() => {
    setPreviewBroken(false);
    if (!attachment || !attachment.type.startsWith("image/") || typeof URL.createObjectURL !== "function") {
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(attachment);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [attachment]);

  useEffect(
    () => () => {
      if (recTimerRef.current) window.clearInterval(recTimerRef.current);
      if (recorderRef.current && recorderRef.current.state !== "inactive") {
        recorderRef.current.stop();
      }
      streamRef.current?.getTracks().forEach((track) => track.stop());
    },
    [],
  );

  function clearAttachment() {
    setAttachment(null);
    setPreviewBroken(false);
    if (fileRef.current) fileRef.current.value = "";
  }

  async function attachFile(picked: File, defaultPrefix = "midia") {
    if (picked.size === 0) {
      setSendError("O arquivo selecionado está vazio.");
      return;
    }
    if (picked.size > MAX_MEDIA_BYTES) {
      setSendError("O arquivo passa do limite de 8 MB permitido para envio.");
      return;
    }
    try {
      let copy = await snapshotFile(picked);
      if (!copy.name || copy.name === "image.png" || copy.name === "blob") {
        const ext = (copy.type.split("/")[1] || "png").split(";")[0];
        copy = new File([copy], `${defaultPrefix}-${Date.now().toString().slice(-5)}.${ext}`, {
          type: copy.type,
          lastModified: copy.lastModified,
        });
      }
      setSendError(null);
      setPreviewBroken(false);
      setAttachment(copy);
      inputRef.current?.focus();
    } catch {
      setSendError("Não foi possível ler o arquivo selecionado. Tente escolhê-lo novamente.");
    }
  }

  async function onFilePicked(event: ChangeEvent<HTMLInputElement>) {
    const picked = event.target.files?.[0];
    if (fileRef.current) fileRef.current.value = "";
    if (!picked) return;
    await attachFile(picked);
  }

  function onPaste(event: ClipboardEvent<HTMLTextAreaElement>) {
    if (blocked || sending || recording) return;
    const dt = event.clipboardData;
    if (!dt) return;
    let pastedFile: File | null = null;
    if (dt.items && dt.items.length > 0) {
      for (const item of Array.from(dt.items)) {
        if (item.kind === "file") {
          const f = item.getAsFile();
          if (f) {
            pastedFile = f;
            break;
          }
        }
      }
    }
    if (!pastedFile && dt.files && dt.files.length > 0) {
      pastedFile = dt.files[0];
    }
    if (pastedFile) {
      event.preventDefault();
      void attachFile(pastedFile, "colado");
    }
  }

  function onDrop(event: DragEvent<HTMLFormElement>) {
    if (blocked || sending || recording) return;
    const f = event.dataTransfer?.files?.[0];
    if (f) {
      event.preventDefault();
      void attachFile(f, "solto");
    }
  }

  function applyQuickReply(item: QuickReply) {
    const owesMe = budgetCtx?.linked_contact ? Number(budgetCtx.linked_contact.owes_me) : 0;
    const pendingFormatted = owesMe > 0 ? money(owesMe) : "R$ 0,00";
    const expanded = expandQuickReply(item.body, {
      nome: chatName,
      telefone: chatPhone,
      chave_pix: budgetCtx?.pix_key,
      valor_pendente: pendingFormatted,
    });
    setDraft(expanded);
    setQuickOpen(false);
    window.setTimeout(() => inputRef.current?.focus(), 20);
  }

  const slashQuery =
    draft.startsWith("/") && !draft.includes("\n") && !draft.includes(" ")
      ? draft.slice(1).toLowerCase()
      : null;

  const filteredQuickReplies =
    slashQuery !== null
      ? quickReplies.filter(
          (r) =>
            r.shortcut.toLowerCase().includes(slashQuery) ||
            r.title.toLowerCase().includes(slashQuery),
        )
      : quickReplies;

  const showQuickMenu = !blocked && (quickOpen || (slashQuery !== null && filteredQuickReplies.length > 0));

  async function toggleRecord() {
    if (blocked || sending) return;
    if (recording) {
      recorderRef.current?.stop();
      return;
    }
    try {
      setSendError(null);
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const preferredMime = MediaRecorder.isTypeSupported("audio/ogg;codecs=opus")
        ? "audio/ogg;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
          ? "audio/webm;codecs=opus"
          : "";
      const recorder = preferredMime
        ? new MediaRecorder(stream, { mimeType: preferredMime })
        : new MediaRecorder(stream);
      recorderRef.current = recorder;
      chunksRef.current = [];
      recorder.ondataavailable = (ev) => {
        if (ev.data.size > 0) chunksRef.current.push(ev.data);
      };
      recorder.onstop = () => {
        if (recTimerRef.current) window.clearInterval(recTimerRef.current);
        recTimerRef.current = null;
        stream.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
        setRecording(false);
        setRecSeconds(0);
        const mime = (recorder.mimeType || "audio/webm").split(";")[0];
        const ext = mime.includes("ogg") ? "ogg" : "webm";
        const blob = new Blob(chunksRef.current, { type: mime });
        chunksRef.current = [];
        if (blob.size === 0) return;
        if (blob.size > MAX_MEDIA_BYTES) {
          setSendError("O áudio gravado passou do limite de 8 MB.");
          return;
        }
        setAttachment(new File([blob], `audio.${ext}`, { type: mime }));
      };
      recorder.start();
      setRecording(true);
      setRecSeconds(0);
      recTimerRef.current = window.setInterval(() => {
        setRecSeconds((sec) => sec + 1);
      }, 1000);
    } catch {
      setSendError("Não foi possível acessar o microfone. Verifique a permissão no navegador.");
    }
  }

  function submitSend(event?: FormEvent) {
    event?.preventDefault();
    if (sending || blocked || recording) return;
    const text = draft.trim();
    if (attachment) {
      setSendError(null);
      sendMediaMutation.mutate(
        {
          file: attachment,
          caption: text || undefined,
          reply_to_id: replyTo?.id ?? null,
        },
        {
          onSuccess: () => {
            setDraft("");
            clearAttachment();
            onCancelReply();
            inputRef.current?.focus();
          },
          onError: (err) => setSendError(errorMessage(err)),
        },
      );
      return;
    }
    if (!text) return;
    setSendError(null);
    sendMutation.mutate(
      { body: text, reply_to_id: replyTo?.id ?? null },
      {
        onSuccess: () => {
          setDraft("");
          onCancelReply();
          inputRef.current?.focus();
        },
        onError: (err) => setSendError(errorMessage(err)),
      },
    );
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Escape" && showQuickMenu) {
      event.preventDefault();
      setQuickOpen(false);
      return;
    }
    if (
      (event.key === "Tab" || (event.key === "Enter" && !event.shiftKey)) &&
      slashQuery !== null &&
      filteredQuickReplies.length > 0
    ) {
      event.preventDefault();
      applyQuickReply(filteredQuickReplies[0]);
      return;
    }
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submitSend();
    }
  }

  const canSend = !blocked && !sending && !recording && (Boolean(attachment) || Boolean(draft.trim()));
  const recFormatted = `${Math.floor(recSeconds / 60)}:${String(recSeconds % 60).padStart(2, "0")}`;

  return (
    <form
      className="wa-composer"
      onSubmit={submitSend}
      onDragOver={(e) => {
        if (!blocked && e.dataTransfer?.types.includes("Files")) e.preventDefault();
      }}
      onDrop={onDrop}
    >
      {blocked && (
        <div className="wa-composer__notice" role="status">
          <span className="wa-composer__notice-text small">
            <WifiOff size={15} aria-hidden />
            Conecte o WhatsApp para enviar mensagens.
          </span>
          <button type="button" className="btn btn--primary btn--sm" onClick={openConnection}>
            Conectar
          </button>
        </div>
      )}
      {showQuickMenu && (
        <QuickReplyMenu
          replies={filteredQuickReplies}
          onSelect={applyQuickReply}
          onClose={() => setQuickOpen(false)}
          onError={setSendError}
        />
      )}
      {replyTo && (
        <div className="wa-reply-bar">
          <div className="wa-reply-bar__text">
            <span className="small muted">Respondendo</span>
            <span className="small">{shortenPreview(replyTo.body, 90)}</span>
          </div>
          <button type="button" className="icon-btn" onClick={onCancelReply} aria-label="Cancelar resposta">
            <X size={16} aria-hidden />
          </button>
        </div>
      )}
      {attachment && (
        <div className="wa-attach-bar">
          <div className="wa-attach-bar__main">
            {previewUrl && !previewBroken ? (
              <img
                src={previewUrl}
                alt=""
                className="wa-attach-bar__thumb"
                onError={() => setPreviewBroken(true)}
              />
            ) : (
              <span className="wa-media-doc__icon" aria-hidden>
                <FileText size={16} />
              </span>
            )}
            <div className="wa-attach-bar__text">
              <strong className="small">{attachment.name}</strong>
              <span className="muted small">{formatBytes(attachment.size)}</span>
            </div>
          </div>
          <button type="button" className="icon-btn" onClick={clearAttachment} aria-label="Remover anexo">
            <X size={16} aria-hidden />
          </button>
        </div>
      )}
      {recording && (
        <div className="wa-rec-pill" role="status">
          <span className="wa-rec-pill__dot" aria-hidden />
          <span className="small">Gravando áudio · {recFormatted}</span>
          <button type="button" className="btn btn--secondary btn--sm" onClick={toggleRecord}>
            Parar
          </button>
        </div>
      )}
      {sendError && (
        <p className="alert alert--error mb-3" role="alert">
          {sendError}
        </p>
      )}
      <div className="wa-composer__row">
        <input
          ref={fileRef}
          type="file"
          className="is-hidden"
          accept="image/*,audio/*,video/*,.pdf,.doc,.docx,.xls,.xlsx,.csv,.txt,.zip"
          onChange={onFilePicked}
        />
        <button
          type="button"
          className="icon-btn wa-composer__tool"
          onClick={() => fileRef.current?.click()}
          disabled={blocked || sending || recording}
          aria-label="Anexar mídia ou documento"
          title="Anexar foto, áudio, vídeo ou documento (ou cole com Ctrl+V)"
        >
          <Paperclip size={18} aria-hidden />
        </button>
        <button
          type="button"
          className={`icon-btn wa-composer__tool ${showQuickMenu ? "is-active" : ""}`}
          onClick={() => setQuickOpen((v) => !v)}
          disabled={blocked || sending || recording}
          aria-label="Respostas rápidas"
          title="Respostas rápidas (/pix, /cobranca, /boasvindas...)"
        >
          <Zap size={17} aria-hidden />
        </button>
        {canRecord && (
          <button
            type="button"
            className={`icon-btn wa-composer__tool ${recording ? "is-recording" : ""}`}
            onClick={toggleRecord}
            disabled={blocked || sending}
            aria-label={recording ? "Parar gravação de áudio" : "Gravar áudio"}
            title={recording ? "Parar gravação" : "Gravar áudio"}
          >
            {recording ? <Square size={16} aria-hidden /> : <Mic size={18} aria-hidden />}
          </button>
        )}
        <label htmlFor="wa-message-input" className="sr-only">
          Mensagem
        </label>
        <textarea
          ref={inputRef}
          id="wa-message-input"
          className="wa-composer__input"
          rows={1}
          placeholder={
            blocked
              ? "WhatsApp desconectado"
              : attachment
                ? "Adicionar legenda (opcional)"
                : "Digite uma mensagem, / para atalhos ou cole mídia (Ctrl+V)"
          }
          value={draft}
          disabled={blocked || recording}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
          onPaste={onPaste}
        />
        <button
          type="submit"
          className="btn btn--primary wa-composer__send"
          disabled={!canSend}
          aria-label="Enviar mensagem"
        >
          <SendHorizontal size={18} aria-hidden />
        </button>
      </div>
    </form>
  );
}
