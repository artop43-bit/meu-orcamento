import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BellRing, CheckCheck, Mail, MailOpen, Megaphone, MessageCircle, Pin } from "lucide-react";
import { Link } from "react-router";

import { errorMessage } from "../api/client";
import { INBOX_KEY, inboxApi, type InboxItem } from "../api/inbox";
import { Badge } from "../components/budget";
import { EmptyGuide } from "../components/help";
import { Alert, Button, LoadingRegion, PageHeader, Skeleton } from "../components/ui";
import { announce } from "../lib/announce";

type Filter = "all" | "unread";

function when(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

function Item({ item, onToggle }: { item: InboxItem; onToggle: (item: InboxItem, read: boolean) => void }) {
  // Fechada até a pessoa abrir; abrir marca como lida.
  const [open, setOpen] = useState(false);
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
              <Link className="btn btn--secondary" to={`/ajustes/solicitacoes/${item.thread_id}`}>
                <MessageCircle size={16} aria-hidden /> Abrir a conversa
              </Link>
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
        </div>
      )}
    </li>
  );
}

/** Caixa de mensagens: respostas às solicitações e recados da administração. */
export default function InboxPage() {
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
      <PageHeader
        title="Mensagens"
        subtitle={unread > 0 ? `${unread} mensagem(ns) não lida(s)` : "Respostas às suas solicitações e recados da administração."}
        actions={
          unread > 0 ? (
            <Button type="button" variant="secondary" onClick={() => void readAll()}>
              <CheckCheck size={16} /> Marcar todas como lidas
            </Button>
          ) : undefined
        }
      />
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
