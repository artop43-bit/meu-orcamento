import { useState, type FormEvent } from "react";
import { Info, Send, Trash2 } from "lucide-react";

import { errorMessage } from "../api/client";
import { inboxApi, type FeedItem } from "../api/inbox";
import { announce } from "../lib/announce";
import { Avatar } from "./media";
import { Alert, Button } from "./ui";

const MAX = 1000;
const NOTICE_KEY = "aviso-respostas-migradas";

function when(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

function noticeSeen(id: string): boolean {
  try {
    return (localStorage.getItem(NOTICE_KEY) ?? "").split(",").includes(id);
  } catch {
    return false;
  }
}

function markNotice(id: string) {
  try {
    const seen = (localStorage.getItem(NOTICE_KEY) ?? "").split(",").filter(Boolean);
    localStorage.setItem(NOTICE_KEY, [...new Set([...seen, id])].join(","));
  } catch {
    // Sem armazenamento: o aviso só volta a aparecer.
  }
}

/**
 * Thread pública de um recado (v1.3.1): respostas de quem recebeu o recado e da administração,
 * com o nome do perfil (nunca o e-mail). Cada pessoa apaga a própria resposta; a administração,
 * qualquer uma.
 */
export function AnnouncementThread({ item, onChange }: { item: FeedItem; onChange: (item: FeedItem) => void }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const migrated = item.replies.some((r) => r.mine && r.migrated);
  const [showNotice, setShowNotice] = useState(() => migrated && !noticeSeen(item.id));

  async function send(event: FormEvent) {
    event.preventDefault();
    if (!text.trim()) {
      setError("Escreva a resposta antes de enviar.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      onChange(await inboxApi.reply(item.id, text.trim()));
      setText("");
      announce("Resposta publicada no recado");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    setError("");
    try {
      await inboxApi.deleteReply(id);
      onChange({ ...item, replies: item.replies.filter((r) => r.id !== id) });
      announce("Resposta apagada");
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <div className="thread">
      {showNotice && (
        <div className="thread__notice" role="status">
          <Info size={16} aria-hidden />
          <span>
            Suas respostas anteriores a este recado agora aparecem aqui, visíveis para todos que receberam o recado. Você pode apagar
            qualquer uma delas.
          </span>
          <button
            type="button"
            className="link-btn small"
            onClick={() => {
              markNotice(item.id);
              setShowNotice(false);
            }}
          >
            Entendi
          </button>
        </div>
      )}
      {item.replies.length > 0 && (
        <ul className="thread__list" aria-label={`Respostas ao recado ${item.title}`}>
          {item.replies.map((reply) => (
            <li key={reply.id} className="thread__reply">
              <Avatar fileId={reply.avatar_id} name={reply.author_name} size={28} />
              <div className="thread__body">
                <p className="thread__meta">
                  <strong>{reply.mine ? "Você" : reply.author_name}</strong>
                  {reply.from_admin && <span className="badge badge--accent">ADM</span>}
                  <span className="muted small">{when(reply.created_at)}</span>
                </p>
                <p className="thread__text">{reply.body}</p>
              </div>
              {reply.can_delete && (
                <button type="button" className="icon-btn" aria-label={`Apagar a resposta de ${reply.mine ? "você" : reply.author_name}`} onClick={() => void remove(reply.id)}>
                  <Trash2 size={15} aria-hidden />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      <Alert tone="error">{error}</Alert>
      <form className="thread__form" onSubmit={send} noValidate>
        <label className="thread__field">
          <span className="sr-only">Responder ao recado {item.title}</span>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={1}
            maxLength={MAX}
            placeholder="Responder ao recado"
          />
        </label>
        <Button type="submit" variant="secondary" loading={busy} aria-label="Publicar resposta">
          <Send size={16} aria-hidden />
        </Button>
      </form>
      {text.length > 0 && (
        <p className="muted small thread__count" aria-live="polite">
          {text.length} / {MAX} · visível para todos que receberam o recado
        </p>
      )}
    </div>
  );
}
