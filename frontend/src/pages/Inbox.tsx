import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BellRing, CheckCheck, Mail, MailOpen, Megaphone, MessageCircle, MessageSquarePlus, Pin, Reply } from "lucide-react";
import { Link, useLocation, useNavigate } from "react-router";

import { errorMessage } from "../api/client";
import { INBOX_KEY, inboxApi, type InboxItem } from "../api/inbox";
import { supportApi } from "../api/support";
import { Badge } from "../components/budget";
import { EmptyGuide } from "../components/help";
import { Composer } from "../components/media";
import { openFeedback } from "../components/power";
import { Alert, Button, LoadingRegion, PageHeader, Skeleton } from "../components/ui";
import { announce } from "../lib/announce";
import { CONVERSATIONS, Conversations } from "./Support";

type Filter = "all" | "unread";

function when(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

function Item({ item, onToggle }: { item: InboxItem; onToggle: (item: InboxItem, read: boolean) => void }) {
  // Fechada até a pessoa abrir; abrir marca como lida.
  const [open, setOpen] = useState(false);
  const [replying, setReplying] = useState(false);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const reply = item.kind === "reply";
  const bodyId = `msg-${item.id}`;

  function expand() {
    const next = !open;
    setOpen(next);
    if (next && !item.read) onToggle(item, true);
  }

  return (
    <li className={`inbox-item ${item.read ? "" : "is-unread"} ${item.important && !item.read ? "is-important" : ""}`}>
      <button type="button" className="inbox-item__head" aria-expanded={open} aria-controls={bodyId} onClick={expand}>
        <span className="inbox-item__icon" aria-hidden>
          {reply ? <MessageCircle size={18} /> : item.kind === "alert" ? <BellRing size={18} /> : <Megaphone size={18} />}
        </span>
        <span className="inbox-item__main">
          <span className="inbox-item__title">
            {!item.read && <span className="sr-only">Não lida: </span>}
            {item.title}
          </span>
          <span className="inbox-item__meta">
            {reply ? "Resposta da administração" : item.kind === "alert" ? "Alerta do orçamento" : "Recado da administração"} · {when(item.created_at)}
          </span>
        </span>
        {item.important && (
          <Badge tone="warn">
            <Pin size={12} aria-hidden /> Importante
          </Badge>
        )}
      </button>
      {open && (
        <div id={bodyId} className="inbox-item__body">
          <p className="inbox-item__text">{item.body}</p>
          <div className="inbox-item__actions">
            {reply && item.thread_id && (
              <Link className="btn btn--secondary" to={`${CONVERSATIONS}/${item.thread_id}`}>
                <MessageCircle size={16} aria-hidden /> Abrir a conversa
              </Link>
            )}
            {item.kind === "announcement" && !replying && (
              <Button type="button" variant="secondary" onClick={() => setReplying(true)}>
                <Reply size={16} aria-hidden /> Responder
              </Button>
            )}
            <Button type="button" variant="secondary" onClick={() => onToggle(item, !item.read)}>
              {item.read ? (
                <>
                  <Mail size={16} aria-hidden /> Marcar como não lida
                </>
              ) : (
                <>
                  <MailOpen size={16} aria-hidden /> Marcar como lida
                </>
              )}
            </Button>
          </div>
          {replying && (
            <div className="inbox-item__reply">
              <Composer
                placeholder="Sua resposta para a administração"
                onSend={async (message, images) => {
                  const thread = await supportApi.replyAnnouncement(item.id, message, images);
                  announce("Resposta enviada");
                  await queryClient.invalidateQueries({ queryKey: ["support"] });
                  navigate(`${CONVERSATIONS}/${thread.id}`);
                }}
              />
            </div>
          )}
        </div>
      )}
    </li>
  );
}

/** Mensagens › Avisos: respostas, recados da administração e alertas. */
function Notices() {
  const queryClient = useQueryClient();
  const items = useQuery({ queryKey: [...INBOX_KEY, "list"], queryFn: inboxApi.list });
  const [filter, setFilter] = useState<Filter>("all");
  const [error, setError] = useState("");
  const list = (items.data ?? []).filter((i) => filter === "all" || !i.read);
  const unread = (items.data ?? []).filter((i) => !i.read).length;

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: INBOX_KEY });
    await queryClient.invalidateQueries({ queryKey: ["support"] });
  }

  async function toggle(item: InboxItem, read: boolean) {
    setError("");
    queryClient.setQueryData<InboxItem[]>([...INBOX_KEY, "list"], (old) => old?.map((i) => (i.id === item.id ? { ...i, read } : i)));
    try {
      await inboxApi.mark(item.id, read);
    } catch (err) {
      setError(errorMessage(err));
    }
    await refresh();
  }

  async function readAll() {
    setError("");
    try {
      await inboxApi.readAll();
      announce("Todas as mensagens marcadas como lidas");
    } catch (err) {
      setError(errorMessage(err));
    }
    await refresh();
  }

  return (
    <>
      {unread > 0 && (
        <div className="row" style={{ marginBottom: 12 }}>
          <span className="muted">{unread} não lida(s)</span>
          <Button type="button" variant="secondary" onClick={() => void readAll()}>
            <CheckCheck size={16} /> Marcar todas como lidas
          </Button>
        </div>
      )}
      <Alert tone="error">{error}</Alert>
      {items.isPending && (
        <LoadingRegion label="Carregando as mensagens">
          <Skeleton height={200} />
        </LoadingRegion>
      )}
      {items.isError && <Alert tone="error">{errorMessage(items.error)}</Alert>}
      {items.data && items.data.length === 0 && (
        <section className="card">
          <EmptyGuide
            icon={<Mail size={22} />}
            title="Nenhuma mensagem"
            text="As respostas às suas solicitações e os recados da administração aparecem aqui. Uma cópia também chega por e-mail, se estiver ligada em Ajustes › Preferências."
          />
        </section>
      )}
      {items.data && items.data.length > 0 && (
        <section className="card stack">
          <div className="segmented" role="radiogroup" aria-label="Filtrar mensagens">
            {(
              [
                ["all", "Todas"],
                ["unread", `Não lidas (${unread})`],
              ] as const
            ).map(([value, label]) => (
              <label key={value}>
                <input type="radio" name="inbox-filter" checked={filter === value} onChange={() => setFilter(value)} />
                {label}
              </label>
            ))}
          </div>
          {list.length === 0 ? (
            <p className="muted" style={{ margin: 0 }}>
              Nenhuma mensagem não lida.
            </p>
          ) : (
            <ul className="inbox-list">
              {list.map((item) => (
                <Item key={item.id} item={item} onToggle={(i, read) => void toggle(i, read)} />
              ))}
            </ul>
          )}
        </section>
      )}
    </>
  );
}

/** Mensagens: avisos (respostas, recados e alertas) e conversas com a administração. */
export default function InboxPage() {
  const location = useLocation();
  const conversations = location.pathname.startsWith(CONVERSATIONS);
  return (
    <>
      <PageHeader
        title="Mensagens"
        subtitle="Avisos, recados da administração e as suas conversas (solicitações numeradas)."
        actions={
          <Button type="button" variant={conversations ? "primary" : "secondary"} onClick={openFeedback}>
            <MessageSquarePlus size={16} /> Nova solicitação
          </Button>
        }
      />
      <nav className="page-tabs no-print" aria-label="Mensagens" style={{ marginBottom: 20 }}>
        <Link to="/mensagens" aria-current={!conversations ? "page" : undefined}>
          Avisos
        </Link>
        <Link to={CONVERSATIONS} aria-current={conversations ? "page" : undefined}>
          Conversas
        </Link>
      </nav>
      {conversations ? <Conversations /> : <Notices />}
    </>
  );
}
