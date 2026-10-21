import { useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Megaphone, MessageSquarePlus, Pin } from "lucide-react";
import { Link, useLocation } from "react-router";

import { errorMessage } from "../api/client";
import { FEED_KEY, INBOX_KEY, inboxApi, type FeedItem } from "../api/inbox";
import { AnnouncementThread } from "../components/AnnouncementThread";
import { Badge } from "../components/budget";
import { EmptyGuide } from "../components/help";
import { openFeedback } from "../components/power";
import { Alert, Button, LoadingRegion, PageHeader, Skeleton } from "../components/ui";
import { CONVERSATIONS, Conversations } from "./Support";

function when(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

/**
 * Mensagens › Recados (v1.3.1): os recados da administração numa lista só, do mais novo ao
 * mais antigo, cada um com a thread pública de respostas logo abaixo.
 */
function Notices() {
  const queryClient = useQueryClient();
  const feed = useQuery({ queryKey: FEED_KEY, queryFn: inboxApi.feed });
  const unread = useQuery({ queryKey: [...INBOX_KEY, "unread"], queryFn: inboxApi.unread });

  // Sem "não lidas" na tela: abrir os recados já conta como lido (o balão do menu zera).
  useEffect(() => {
    if ((unread.data?.unread ?? 0) > 0) {
      void inboxApi.readAll().then(() => queryClient.invalidateQueries({ queryKey: INBOX_KEY }));
    }
  }, [unread.data?.unread, queryClient]);

  function update(item: FeedItem) {
    queryClient.setQueryData<FeedItem[]>(FEED_KEY, (list) => list?.map((i) => (i.id === item.id ? item : i)));
  }

  if (feed.isPending) {
    return (
      <LoadingRegion label="Carregando os recados">
        <Skeleton height={200} />
      </LoadingRegion>
    );
  }
  if (feed.isError) return <Alert tone="error">{errorMessage(feed.error)}</Alert>;
  if (feed.data.length === 0) {
    return (
      <section className="card">
        <EmptyGuide
          icon={<Megaphone size={22} />}
          title="Nenhum recado ainda"
          text="Os recados da administração aparecem aqui, com espaço para responder. Uma cópia também chega por e-mail, se estiver ligada em Ajustes › Preferências."
        />
      </section>
    );
  }
  return (
    <ul className="notice-list">
      {feed.data.map((item) => (
        <li key={item.id} className={`card notice ${item.important ? "is-important" : ""}`}>
          <div className="notice__head">
            <span className="inbox-item__icon" aria-hidden>
              <Megaphone size={18} />
            </span>
            <div className="notice__title">
              <h2>{item.title}</h2>
              <span className="muted small">Recado da administração · {when(item.created_at)}</span>
            </div>
            {item.important && (
              <Badge tone="warn">
                <Pin size={12} aria-hidden /> Importante
              </Badge>
            )}
          </div>
          <p className="notice__body">{item.body}</p>
          <AnnouncementThread item={item} onChange={update} />
        </li>
      ))}
    </ul>
  );
}

/** Mensagens: recados da administração e as suas solicitações (numeradas). */
export default function InboxPage() {
  const location = useLocation();
  const requests = location.pathname.startsWith(CONVERSATIONS);
  return (
    <>
      <PageHeader
        title="Mensagens"
        subtitle="Recados da administração e as suas solicitações."
        actions={
          // A nova solicitação fica só na aba Solicitações (v1.3.2).
          requests ? (
            <Button type="button" onClick={openFeedback}>
              <MessageSquarePlus size={16} /> Nova solicitação
            </Button>
          ) : undefined
        }
      />
      <nav className="page-tabs no-print" aria-label="Mensagens" style={{ marginBottom: 20 }}>
        <Link to="/mensagens" aria-current={!requests ? "page" : undefined}>
          Recados
        </Link>
        <Link to={CONVERSATIONS} aria-current={requests ? "page" : undefined}>
          Solicitações
        </Link>
      </nav>
      {requests ? <Conversations /> : <Notices />}
    </>
  );
}
