import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bug, Check } from "lucide-react";

import { api, errorMessage } from "../api/client";
import { Alert, Button, LoadingRegion, Skeleton } from "../components/ui";
import { announce } from "../lib/announce";

type ErrorEvent = {
  id: string;
  source: "web" | "api";
  name: string;
  message: string;
  path: string | null;
  detail: string | null;
  user_agent: string | null;
  release: string | null;
  count: number;
  first_seen: string;
  last_seen: string;
  resolved_at: string | null;
};

const KEY = ["admin", "errors"] as const;

function when(iso: string) {
  return new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

function device(agent: string | null): string {
  if (!agent) return "aparelho não informado";
  const system = /Android/.test(agent) ? "Android" : /iPhone|iPad/.test(agent) ? "iPhone" : /Windows/.test(agent) ? "Windows" : /Mac OS/.test(agent) ? "macOS" : "Linux";
  const browser = /Edg\//.test(agent) ? "Edge" : /Firefox/.test(agent) ? "Firefox" : /Chrome/.test(agent) ? "Chrome" : /Safari/.test(agent) ? "Safari" : "navegador";
  return `${browser} no ${system}`;
}

/** Administração › Erros: o que quebrou nas telas e no servidor, agrupado (v1.3). */
export default function AdminErrors() {
  const queryClient = useQueryClient();
  const list = useQuery({ queryKey: KEY, queryFn: () => api.get<ErrorEvent[]>("/admin/errors"), refetchInterval: 60_000 });
  const open = (list.data ?? []).filter((e) => !e.resolved_at);
  const resolved = (list.data ?? []).filter((e) => e.resolved_at);

  async function resolve(event: ErrorEvent) {
    await api.post(`/admin/errors/${event.id}/resolve`);
    await queryClient.invalidateQueries({ queryKey: KEY });
    announce("Erro marcado como resolvido");
  }

  if (list.isPending) {
    return (
      <LoadingRegion label="Carregando os erros">
        <Skeleton height={160} />
      </LoadingRegion>
    );
  }
  if (list.isError) return <Alert tone="error">{errorMessage(list.error)}</Alert>;

  return (
    <div className="stack">
      <p className="muted small" style={{ margin: 0 }}>
        Erros das telas e do servidor, agrupados. Números, e-mails e identificadores aparecem mascarados. Se o erro voltar depois de
        resolvido, ele reabre sozinho. Grupos sem novidade há 90 dias são apagados.
      </p>
      {open.length === 0 && (
        <section className="card">
          <p style={{ margin: 0 }}>
            <Check size={16} aria-hidden /> Nenhum erro em aberto.
          </p>
        </section>
      )}
      {open.map((event) => (
        <ErrorCard key={event.id} event={event} onResolve={() => void resolve(event)} />
      ))}
      {resolved.length > 0 && (
        <details className="more">
          <summary>Resolvidos ({resolved.length})</summary>
          <div className="stack" style={{ marginTop: 12 }}>
            {resolved.map((event) => (
              <ErrorCard key={event.id} event={event} />
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

function ErrorCard({ event, onResolve }: { event: ErrorEvent; onResolve?: () => void }) {
  return (
    <article className="card stack error-card">
      <div className="section-header">
        <h3 className="error-card__title">
          <Bug size={16} aria-hidden /> {event.name}
          <span className={`badge ${event.source === "api" ? "badge--warn" : "badge--info"}`}>{event.source === "api" ? "Servidor" : "Tela"}</span>
          <span className="badge badge--muted">{event.count}×</span>
        </h3>
        {onResolve && (
          <Button type="button" variant="secondary" onClick={onResolve}>
            Marcar como resolvido
          </Button>
        )}
      </div>
      <p className="error-card__message">{event.message}</p>
      <p className="muted small" style={{ margin: 0 }}>
        {event.path ?? "tela não informada"} · última vez em {when(event.last_seen)} · primeira em {when(event.first_seen)}
        {event.release && ` · versão ${event.release}`} · {device(event.user_agent)}
      </p>
      {event.detail && (
        <details>
          <summary className="small">Detalhes técnicos</summary>
          <pre className="error-card__detail">{event.detail}</pre>
        </details>
      )}
    </article>
  );
}
