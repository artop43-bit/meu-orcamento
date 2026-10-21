import { useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ChevronLeft, MessagesSquare, MessageSquarePlus } from "lucide-react";
import { Link, Navigate, useParams } from "react-router";

import { errorMessage } from "../api/client";
import { INBOX_KEY } from "../api/inbox";
import { KIND_LABEL, STATUS_LABEL, supportApi, type Thread, type ThreadStatus } from "../api/support";
import { EmptyGuide } from "../components/help";
import { Composer, Conversation } from "../components/media";
import { openFeedback } from "../components/power";
import { Alert, Button, LoadingRegion, Skeleton } from "../components/ui";

export const STATUS_TONE: Record<ThreadStatus, string> = {
  open: "badge--warn",
  in_progress: "badge--accent",
  planned: "badge--info",
  answered: "badge--accent",
  resolved: "badge--ok",
  declined: "badge--muted",
};

export const CONVERSATIONS = "/mensagens/conversas";

export function shortWhen(iso: string): string {
  const date = new Date(iso);
  const today = new Date();
  return date.toDateString() === today.toDateString()
    ? date.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })
    : date.toLocaleDateString("pt-BR");
}

/** "Planejada · versão 1.2" */
export function statusText(t: Pick<Thread, "status" | "planned_version">): string {
  return t.status === "planned" && t.planned_version ? `${STATUS_LABEL[t.status]} · versão ${t.planned_version}` : STATUS_LABEL[t.status];
}

function ThreadList({ threads, current }: { threads: Thread[]; current?: string }) {
  return (
    <ul className="thread-list">
      {threads.map((t) => (
        <li key={t.id}>
          <Link
            to={`${CONVERSATIONS}/${t.id}`}
            className={`thread-list__item ${t.unread ? "is-unread" : ""}`}
            aria-current={current === t.id ? "page" : undefined}
          >
            <span className="thread-list__top">
              <strong className="thread-list__title">
                <span className="thread-number">#{t.number}</span> {t.title}
              </strong>
              <time className="muted small" dateTime={t.last_message_at}>
                {shortWhen(t.last_message_at)}
              </time>
            </span>
            <span className="thread-list__meta">
              <span className={`badge ${STATUS_TONE[t.status]}`}>{statusText(t)}</span>
              <span className="muted small">{t.announcement_id ? "Resposta a recado" : KIND_LABEL[t.kind]}</span>
              {t.unread && <span className="badge badge--accent">Resposta nova</span>}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

function ThreadView({ id }: { id: string }) {
  const queryClient = useQueryClient();
  const thread = useQuery({ queryKey: ["support", "thread", id], queryFn: () => supportApi.thread(id) });

  // Abrir a conversa marca as respostas como lidas: atualiza a lista e o aviso do menu
  // (inclusive a caixa de Mensagens, que recebe a mesma resposta).
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["support"] });
  const loaded = thread.isSuccess;
  useEffect(() => {
    if (loaded) void queryClient.invalidateQueries({ queryKey: INBOX_KEY });
  }, [loaded, id, queryClient]);

  if (thread.isPending)
    return (
      <LoadingRegion label="Carregando a conversa">
        <Skeleton height={240} />
      </LoadingRegion>
    );
  if (thread.isError) return <Alert tone="error">{errorMessage(thread.error)}</Alert>;
  const data = thread.data;
  const closed = data.status === "resolved" || data.status === "declined";
  return (
    <section className="card thread-view" aria-labelledby="thread-title">
      <header className="thread-view__header">
        <Link to={CONVERSATIONS} className="thread-view__back small">
          <ChevronLeft size={16} aria-hidden /> Todas as conversas
        </Link>
        <h2 id="thread-title">
          <span className="thread-number">#{data.number}</span> {data.title}
        </h2>
        <p className="thread-list__meta">
          <span className={`badge ${STATUS_TONE[data.status]}`}>{statusText(data)}</span>
          <span className="muted small">{data.announcement_id ? "Resposta a recado" : KIND_LABEL[data.kind]}</span>
        </p>
        {data.status_note && <p className="thread-view__status-note">{data.status_note}</p>}
      </header>
      <Conversation messages={data.messages} viewer="user" userName="Você" />
      {closed && <p className="muted small thread-view__note">Conversa encerrada. Uma nova mensagem a reabre.</p>}
      <Composer
        onSend={async (message, images) => {
          const updated = await supportApi.reply(id, message, images);
          queryClient.setQueryData(["support", "thread", id], updated);
          await refresh();
        }}
      />
      {!closed && (
        <div className="thread-view__actions">
          <Button
            type="button"
            variant="secondary"
            onClick={async () => {
              await supportApi.resolve(id);
              await refresh();
            }}
          >
            <CheckCircle2 size={16} /> Marcar como resolvida
          </Button>
        </div>
      )}
    </section>
  );
}

/** Mensagens › Solicitações: os pedidos numerados, com a conversa com a administração. */
export function Conversations() {
  const { id } = useParams();
  const threads = useQuery({ queryKey: ["support", "mine"], queryFn: supportApi.mine });
  const list = threads.data ?? [];

  return (
    <>
      {threads.isPending && (
        <LoadingRegion label="Carregando as conversas">
          <Skeleton height={160} />
        </LoadingRegion>
      )}
      {threads.isError && <Alert tone="error">{errorMessage(threads.error)}</Alert>}
      {threads.data && list.length === 0 && (
        <section className="card">
          <EmptyGuide
            icon={<MessagesSquare size={22} />}
            title="Nenhuma conversa ainda"
            text="Envie sugestões, relate problemas ou tire dúvidas com “Nova solicitação”, ou responda um recado da administração. Cada solicitação ganha um número para acompanhar o andamento."
            action={
              <Button type="button" onClick={openFeedback}>
                <MessageSquarePlus size={16} /> Nova solicitação
              </Button>
            }
          />
        </section>
      )}
      {list.length > 0 && (
        <div className={`support-layout ${id ? "has-thread" : ""}`}>
          <section className="card support-layout__list" aria-label="Solicitações">
            <ThreadList threads={list} current={id} />
          </section>
          <div className="support-layout__detail">
            {id ? <ThreadView key={id} id={id} /> : <p className="muted support-layout__hint">Selecione uma conversa.</p>}
          </div>
        </div>
      )}
      {id && threads.data && list.length === 0 && <ThreadView key={id} id={id} />}
    </>
  );
}

/** Endereço antigo (Ajustes › Minhas solicitações): leva para Mensagens › Solicitações. */
export default function SupportRedirect() {
  const { id } = useParams();
  return <Navigate to={id ? `${CONVERSATIONS}/${id}` : CONVERSATIONS} replace />;
}
