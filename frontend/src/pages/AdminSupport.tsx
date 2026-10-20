import { useEffect, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, Search } from "lucide-react";
import { useSearchParams } from "react-router";

import { errorMessage } from "../api/client";
import {
  KIND_LABEL,
  STATUS_LABEL,
  STATUSES,
  supportApi,
  type AdminThread,
  type AdminThreadDetail,
  type ThreadKind,
  type ThreadStatus,
} from "../api/support";
import { Avatar, Composer, Conversation } from "../components/media";
import { Alert, Button, LoadingRegion, Sheet, Skeleton } from "../components/ui";
import { announce } from "../lib/announce";
import { shortWhen, STATUS_TONE, statusText } from "./Support";

type View = "recentes" | "usuarios" | "status" | "quadro";
const VIEWS: [View, string][] = [
  ["recentes", "Recentes"],
  ["usuarios", "Por usuário"],
  ["status", "Por status"],
  ["quadro", "Quadro"],
];
const KINDS: ThreadKind[] = ["idea", "bug", "other"];

function personName(p: AdminThread["user"]): string {
  return p.display_name || p.email;
}

function origin(t: AdminThread): string {
  return t.announcement_id ? "Resposta a recado" : KIND_LABEL[t.kind];
}

function ThreadRows({ threads, current, onOpen }: { threads: AdminThread[]; current: string | null; onOpen: (id: string) => void }) {
  if (threads.length === 0) return <p className="muted">Nenhuma solicitação neste filtro.</p>;
  return (
    <ul className="thread-list">
      {threads.map((t) => (
        <li key={t.id}>
          <button
            type="button"
            className={`thread-list__item ${t.unread ? "is-unread" : ""}`}
            aria-current={current === t.id ? "true" : undefined}
            onClick={() => onOpen(t.id)}
          >
            <span className="thread-list__top">
              <span className="thread-list__who">
                <Avatar fileId={t.user.avatar_id} name={personName(t.user)} size={28} />
                <strong className="thread-list__title">
                  <span className="thread-number">#{t.number}</span> {t.title}
                </strong>
              </span>
              <time className="muted small" dateTime={t.last_message_at}>
                {shortWhen(t.last_message_at)}
              </time>
            </span>
            <span className="thread-list__meta">
              <span className={`badge ${STATUS_TONE[t.status]}`}>{statusText(t)}</span>
              <span className="muted small">
                {origin(t)} · {personName(t.user)} · {t.messages_count} mensagem(ns)
              </span>
              {t.unread && <span className="badge badge--accent">Não lida</span>}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

/** Quadro de tarefas: uma coluna por status. */
function Board({ threads, onOpen }: { threads: AdminThread[]; onOpen: (id: string) => void }) {
  return (
    <div className="task-board" role="region" aria-label="Quadro de tarefas" tabIndex={0}>
      {STATUSES.map((status) => {
        const column = threads.filter((t) => t.status === status);
        return (
          <section key={status} className="task-board__column" aria-label={`${STATUS_LABEL[status]} (${column.length})`}>
            <h3 className="task-board__title">
              <span className={`badge ${STATUS_TONE[status]}`}>{STATUS_LABEL[status]}</span>
              <span className="muted small">{column.length}</span>
            </h3>
            <ul className="task-board__cards">
              {column.map((t) => (
                <li key={t.id}>
                  <button type="button" className={`task-card ${t.unread ? "is-unread" : ""}`} onClick={() => onOpen(t.id)}>
                    <span className="task-card__top">
                      <span className="thread-number">#{t.number}</span>
                      {t.planned_version && <span className="badge">v{t.planned_version}</span>}
                    </span>
                    <strong className="task-card__title">{t.title}</strong>
                    <span className="muted small">
                      {origin(t)} · {personName(t.user)}
                    </span>
                  </button>
                </li>
              ))}
              {column.length === 0 && <li className="muted small task-board__empty">Nada aqui.</li>}
            </ul>
          </section>
        );
      })}
    </div>
  );
}

function StatusForm({ data, onSaved }: { data: AdminThreadDetail; onSaved: (updated: AdminThreadDetail) => void }) {
  const versions = useQuery({ queryKey: ["admin", "support", "versions"], queryFn: supportApi.adminVersions });
  const [status, setStatus] = useState<ThreadStatus>(data.status);
  const [version, setVersion] = useState(data.planned_version ?? "");
  const [note, setNote] = useState(data.status_note ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const changed = status !== data.status || version !== (data.planned_version ?? "") || note !== (data.status_note ?? "");

  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const updated = await supportApi.adminStatus(data.id, { status, version: version || null, note: note || null });
      onSaved(updated);
      announce(`#${data.number}: ${STATUS_LABEL[status]}`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="task-status" onSubmit={save} aria-label={`Andamento da solicitação #${data.number}`}>
      <Alert tone="error">{error}</Alert>
      <label>
        Status
        <select value={status} onChange={(e) => setStatus(e.target.value as ThreadStatus)}>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {STATUS_LABEL[s]}
            </option>
          ))}
        </select>
      </label>
      <label>
        Versão
        <input value={version} onChange={(e) => setVersion(e.target.value)} list="task-versions" maxLength={20} placeholder="Ex.: 1.2" />
        <datalist id="task-versions">
          {(versions.data ?? []).map((v) => (
            <option key={v} value={v} />
          ))}
        </datalist>
      </label>
      <label className="task-status__note">
        Nota para a pessoa (opcional)
        <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={200} placeholder="Ex.: Entra na próxima versão." />
      </label>
      <Button type="submit" variant="secondary" loading={busy} disabled={!changed}>
        Salvar status
      </Button>
    </form>
  );
}

function AdminThreadPanel({ id, onBack }: { id: string; onBack: () => void }) {
  const queryClient = useQueryClient();
  const thread = useQuery({ queryKey: ["admin", "support", "thread", id], queryFn: () => supportApi.adminThread(id) });

  // Abrir marca como lida: atualiza contadores e listas.
  useEffect(() => {
    if (thread.data) void queryClient.invalidateQueries({ queryKey: ["admin", "support", "list"] });
  }, [thread.data, queryClient]);

  if (thread.isPending)
    return (
      <LoadingRegion label="Carregando a conversa">
        <Skeleton height={240} />
      </LoadingRegion>
    );
  if (thread.isError) return <Alert tone="error">{errorMessage(thread.error)}</Alert>;
  const data = thread.data;
  const name = personName(data.user);

  async function saved(updated: AdminThreadDetail) {
    queryClient.setQueryData(["admin", "support", "thread", id], updated);
    await queryClient.invalidateQueries({ queryKey: ["admin"] });
  }

  return (
    <section className="card thread-view" aria-labelledby="admin-thread-title">
      <header className="thread-view__header">
        <button type="button" className="link-btn thread-view__back small" onClick={onBack}>
          <ChevronLeft size={16} aria-hidden /> Voltar à lista
        </button>
        <div className="thread-view__person">
          <Avatar fileId={data.user.avatar_id} name={name} size={40} />
          <span>
            <strong>{name}</strong>
            {data.user.display_name && <span className="muted small"> · {data.user.email}</span>}
            <span className="muted small thread-view__context">
              {origin(data)} · enviada em {new Date(data.created_at).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })}
              {data.page && ` · tela ${data.page}`}
              {data.app_version && ` · versão ${data.app_version}`}
            </span>
          </span>
        </div>
        <h2 id="admin-thread-title">
          <span className="thread-number">#{data.number}</span> {data.title}
        </h2>
        <StatusForm key={`${data.status}-${data.planned_version}-${data.status_note}`} data={data} onSaved={(u) => void saved(u)} />
      </header>
      <Conversation messages={data.messages} viewer="admin" userName={name} />
      <Composer
        placeholder="Responder (a pessoa vê em Mensagens › Conversas)"
        onSend={async (message, images) => {
          const updated = await supportApi.adminReply(id, message, images);
          await saved(updated);
        }}
      />
    </section>
  );
}

export default function AdminSupport() {
  const [params, setParams] = useSearchParams();
  const view = (VIEWS.find(([v]) => v === params.get("visao"))?.[0] ?? "recentes") as View;
  const status = (STATUSES.find((s) => s === params.get("status")) ?? null) as ThreadStatus | null;
  const kind = (KINDS.find((k) => k === params.get("tipo")) ?? null) as ThreadKind | null;
  const version = params.get("versao");
  const userId = params.get("usuario");
  const current = params.get("id");
  const [text, setText] = useState(params.get("q") ?? "");
  const q = params.get("q") ?? "";

  function update(changes: Record<string, string | null>) {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    next.set("aba", "solicitacoes");
    setParams(next, { replace: true });
  }

  // Busca enquanto digita (com uma pequena espera).
  useEffect(() => {
    const timer = window.setTimeout(() => {
      if (text.trim() !== q) update({ q: text.trim() || null });
    }, 300);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text]);

  const counts = useQuery({ queryKey: ["admin", "support", "list", "counts"], queryFn: supportApi.adminCounts, refetchInterval: 60_000 });
  const versions = useQuery({ queryKey: ["admin", "support", "versions"], queryFn: supportApi.adminVersions });
  const showPeople = view === "usuarios" && !userId;
  const people = useQuery({
    queryKey: ["admin", "support", "list", "people", q],
    queryFn: () => supportApi.adminPeople(q || undefined),
    enabled: showPeople,
  });
  const effectiveStatus = view === "status" ? (status ?? "open") : null;
  const threads = useQuery({
    queryKey: ["admin", "support", "list", "threads", q, effectiveStatus, view === "usuarios" ? userId : null, kind, version],
    queryFn: () =>
      supportApi.adminThreads({
        q: q || undefined,
        status: effectiveStatus ?? undefined,
        user_id: view === "usuarios" ? (userId ?? undefined) : undefined,
        kind: kind ?? undefined,
        version: version ?? undefined,
      }),
    enabled: !showPeople,
    refetchInterval: 60_000,
  });
  const selectedPerson = userId ? threads.data?.[0]?.user : null;

  const filters = (
    <div className="task-filters">
      <label>
        <span className="sr-only">Tipo</span>
        <select value={kind ?? ""} onChange={(e) => update({ tipo: e.target.value || null })} aria-label="Filtrar por tipo">
          <option value="">Todos os tipos</option>
          {KINDS.map((k) => (
            <option key={k} value={k}>
              {KIND_LABEL[k]}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span className="sr-only">Versão</span>
        <select value={version ?? ""} onChange={(e) => update({ versao: e.target.value || null })} aria-label="Filtrar por versão planejada">
          <option value="">Todas as versões</option>
          {(versions.data ?? []).map((v) => (
            <option key={v} value={v}>
              Versão {v}
            </option>
          ))}
        </select>
      </label>
    </div>
  );

  const tabs = (
    <div className="segmented segmented--4" role="tablist" aria-label="Organizar por">
      {VIEWS.map(([value, label]) => (
        <button
          key={value}
          type="button"
          role="tab"
          aria-selected={view === value}
          className={view === value ? "is-active" : undefined}
          onClick={() => update({ visao: value, status: null, usuario: null })}
        >
          {label}
        </button>
      ))}
    </div>
  );

  const search = (
    <label className="list-tools__search">
      <Search size={16} aria-hidden />
      <span className="sr-only">Buscar solicitações</span>
      <input type="search" value={text} onChange={(e) => setText(e.target.value)} placeholder="Buscar por #número, assunto, mensagem ou e-mail" />
    </label>
  );

  if (view === "quadro") {
    return (
      <div className="stack">
        <section className="card stack">
          {tabs}
          {search}
          {filters}
        </section>
        {threads.isPending && <Skeleton height={240} />}
        {threads.isError && <Alert tone="error">{errorMessage(threads.error)}</Alert>}
        {threads.data && <Board threads={threads.data} onOpen={(id) => update({ id })} />}
        <Sheet open={Boolean(current)} title="Solicitação" onClose={() => update({ id: null })} wide>
          {current && <AdminThreadPanel key={current} id={current} onBack={() => update({ id: null })} />}
        </Sheet>
      </div>
    );
  }

  return (
    <div className={`support-layout support-layout--admin ${current ? "has-thread" : ""}`}>
      <section className="card stack support-layout__list" aria-label="Solicitações recebidas">
        {tabs}
        {search}
        {filters}

        {view === "status" && (
          <div className="chips" role="group" aria-label="Status">
            {STATUSES.map((s) => (
              <button
                key={s}
                type="button"
                className={`chip-btn ${effectiveStatus === s ? "is-active" : ""}`}
                aria-pressed={effectiveStatus === s}
                onClick={() => update({ status: s })}
              >
                {STATUS_LABEL[s]} {counts.data ? `(${counts.data[s]})` : ""}
              </button>
            ))}
          </div>
        )}

        {view === "usuarios" && userId && (
          <button type="button" className="link-btn small" onClick={() => update({ usuario: null })}>
            <ChevronLeft size={14} aria-hidden /> Todas as pessoas {selectedPerson ? `· ${personName(selectedPerson)}` : ""}
          </button>
        )}

        {showPeople ? (
          <>
            {people.isPending && <Skeleton height={120} />}
            {people.isError && <Alert tone="error">{errorMessage(people.error)}</Alert>}
            {people.data && people.data.length === 0 && <p className="muted">Ninguém encontrado.</p>}
            <ul className="thread-list">
              {people.data?.map((p) => (
                <li key={p.user.id}>
                  <button type="button" className={`thread-list__item ${p.unread ? "is-unread" : ""}`} onClick={() => update({ usuario: p.user.id })}>
                    <span className="thread-list__top">
                      <span className="thread-list__who">
                        <Avatar fileId={p.user.avatar_id} name={personName(p.user)} size={28} />
                        <strong className="thread-list__title">{personName(p.user)}</strong>
                      </span>
                      <time className="muted small" dateTime={p.last_message_at}>
                        {shortWhen(p.last_message_at)}
                      </time>
                    </span>
                    <span className="thread-list__meta muted small">
                      {p.total} solicitação(ões) · {p.open} aberta(s)
                      {p.unread > 0 && <span className="badge badge--accent">{p.unread} não lida(s)</span>}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <>
            {threads.isPending && <Skeleton height={160} />}
            {threads.isError && <Alert tone="error">{errorMessage(threads.error)}</Alert>}
            {threads.data && <ThreadRows threads={threads.data} current={current} onOpen={(id) => update({ id })} />}
          </>
        )}
      </section>
      <div className="support-layout__detail">
        {current ? (
          <AdminThreadPanel key={current} id={current} onBack={() => update({ id: null })} />
        ) : (
          <p className="muted support-layout__hint">
            {counts.data ? `${counts.data.unread} não lida(s) · ${counts.data.open} aberta(s). ` : ""}Selecione uma solicitação para responder.
          </p>
        )}
      </div>
    </div>
  );
}
