import { useEffect, useId, useMemo, useRef, useState, type FormEvent } from "react";
import { ImagePlus, Paperclip, Send, X } from "lucide-react";

import { fileUrl, IMAGE_ACCEPT, MAX_IMAGE_MB, MAX_IMAGES, checkImage, type Message } from "../api/support";
import { errorMessage } from "../api/client";
import { Alert, Button, Sheet } from "./ui";

/** Foto do perfil (ou iniciais, sem foto). */
export function Avatar({
  fileId,
  name,
  size = 40,
  className,
}: {
  fileId: string | null | undefined;
  name: string;
  size?: number;
  className?: string;
}) {
  const initials =
    name
      .replace(/@.*/, "")
      .split(/[\s._-]+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]!.toUpperCase())
      .join("") || "?";
  return (
    <span className={`avatar ${className ?? ""}`} style={{ width: size, height: size, fontSize: size * 0.4 }} aria-hidden>
      {fileId ? <img src={fileUrl(fileId)} alt="" loading="lazy" decoding="async" /> : initials}
    </span>
  );
}

/** Miniaturas das imagens de uma mensagem; um toque amplia. */
export function AttachmentGrid({ items }: { items: Message["attachments"] }) {
  const [open, setOpen] = useState<string | null>(null);
  if (!items.length) return null;
  return (
    <>
      <div className="attachments">
        {items.map((item, index) => (
          <button key={item.id} type="button" className="attachments__item" onClick={() => setOpen(item.id)} aria-label={`Ampliar imagem ${index + 1}`}>
            <img src={fileUrl(item.id)} alt={`Imagem anexada ${index + 1}`} loading="lazy" decoding="async" width={item.width} height={item.height} />
          </button>
        ))}
      </div>
      <Sheet open={open !== null} title="Imagem anexada" onClose={() => setOpen(null)} wide>
        {open && (
          <div className="lightbox">
            <img src={fileUrl(open)} alt="Imagem anexada ampliada" />
            <a className="small" href={fileUrl(open)} target="_blank" rel="noreferrer">
              Abrir em tamanho original
            </a>
          </div>
        )}
      </Sheet>
    </>
  );
}

/**
 * Seleção de imagens para anexar: até 3, com prévia e remoção. No celular, o seletor do
 * sistema oferece câmera e galeria.
 */
export function ImagePicker({ files, onChange }: { files: File[]; onChange: (files: File[]) => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState("");
  const hintId = useId();
  const previews = useMemo(() => files.map((f) => URL.createObjectURL(f)), [files]);
  useEffect(() => () => previews.forEach((url) => URL.revokeObjectURL(url)), [previews]);

  function add(list: FileList | null) {
    if (!list) return;
    const problems: string[] = [];
    const next = [...files];
    for (const file of Array.from(list)) {
      const problem = checkImage(file);
      if (problem) problems.push(problem);
      else if (next.length >= MAX_IMAGES) problems.push(`Limite de ${MAX_IMAGES} imagens por mensagem.`);
      else next.push(file);
    }
    setError([...new Set(problems)].join(" "));
    onChange(next);
    if (inputRef.current) inputRef.current.value = "";
  }

  return (
    <div className="image-picker">
      <div className="image-picker__row">
        <Button
          type="button"
          variant="secondary"
          onClick={() => inputRef.current?.click()}
          disabled={files.length >= MAX_IMAGES}
          aria-describedby={hintId}
        >
          <ImagePlus size={16} /> Anexar imagem
        </Button>
        <span id={hintId} className="muted small">
          Até {MAX_IMAGES} imagens (PNG, JPG, WebP ou GIF, até {MAX_IMAGE_MB} MB cada).
        </span>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept={IMAGE_ACCEPT}
        multiple
        hidden
        onChange={(e) => add(e.target.files)}
        aria-label="Escolher imagens"
        data-testid="image-input"
      />
      {error && (
        <small className="field-error" role="alert">
          {error}
        </small>
      )}
      {files.length > 0 && (
        <ul className="image-picker__list">
          {files.map((file, index) => (
            <li key={`${file.name}-${index}`}>
              <img src={previews[index]} alt={`Prévia: ${file.name}`} />
              <button
                type="button"
                className="icon-btn image-picker__remove"
                aria-label={`Remover ${file.name}`}
                onClick={() => onChange(files.filter((_, i) => i !== index))}
              >
                <X size={16} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function when(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

/** Linha do tempo da conversa: mensagens do usuário à direita, da administração à esquerda. */
export function Conversation({
  messages,
  viewer,
  userName,
}: {
  messages: Message[];
  viewer: "user" | "admin";
  userName: string;
}) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length]);
  return (
    <ol className="conversation" aria-label="Mensagens">
      {messages.map((m) => {
        const mine = viewer === "admin" ? m.from_admin : !m.from_admin;
        const author = m.from_admin ? "Administração" : viewer === "admin" ? userName : "Você";
        return (
          <li key={m.id} className={`bubble ${mine ? "bubble--mine" : "bubble--other"}`}>
            <span className="bubble__meta">
              <strong>{author}</strong> · <time dateTime={m.created_at}>{when(m.created_at)}</time>
            </span>
            <p className="bubble__text">{m.body}</p>
            <AttachmentGrid items={m.attachments} />
          </li>
        );
      })}
      <div ref={endRef} />
    </ol>
  );
}

/** Caixa de resposta com anexos; fica fixa no rodapé da conversa no celular. */
export function Composer({
  onSend,
  placeholder = "Escreva a sua mensagem",
  disabledReason,
}: {
  onSend: (message: string, images: File[]) => Promise<unknown>;
  placeholder?: string;
  disabledReason?: string;
}) {
  const [text, setText] = useState("");
  const [images, setImages] = useState<File[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [showPicker, setShowPicker] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!text.trim()) {
      setError("Escreva a mensagem antes de enviar.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await onSend(text.trim(), images);
      setText("");
      setImages([]);
      setShowPicker(false);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="composer" onSubmit={submit} noValidate>
      {disabledReason && <p className="muted small">{disabledReason}</p>}
      <Alert tone="error">{error}</Alert>
      {(showPicker || images.length > 0) && <ImagePicker files={images} onChange={setImages} />}
      <div className="composer__row">
        <button
          type="button"
          className="icon-btn"
          aria-label="Anexar imagens"
          aria-pressed={showPicker || images.length > 0}
          onClick={() => setShowPicker((v) => !v)}
        >
          <Paperclip size={18} />
        </button>
        <label className="composer__field">
          <span className="sr-only">Mensagem</span>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={2}
            maxLength={4000}
            placeholder={placeholder}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                e.currentTarget.form?.requestSubmit();
              }
            }}
          />
        </label>
        <Button type="submit" loading={busy} aria-label="Enviar mensagem">
          <Send size={16} /> <span className="composer__send-label">Enviar</span>
        </Button>
      </div>
    </form>
  );
}
