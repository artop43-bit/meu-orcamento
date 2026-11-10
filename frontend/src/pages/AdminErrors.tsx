import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bug, Check, Gauge } from "lucide-react";

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

type PerfRow = { screen: string; count: number; average_ms: number; max_ms: number; slow_pct: number; frame_ms: number };

const SCREEN_NAMES: Record<string, string> = {
  orcamento: "Orçamento",
  calendario: "Calendário",
  cartoes: "Cartões",
  contas: "Contas",
  revisar: "Revisar",
  busca: "Busca",
  mensagens: "Mensagens",
  dividas: "Dívidas",
  divisoes: "Divisões",
  metas: "Metas",
  historico: "Histórico",
  analises: "Insights",
  investimentos: "Investimentos",
  ajustes: "Ajustes",
  relatorio: "Relatório",
  admin: "Administração",
  outras: "Outras",
};

const seconds = (ms: number) => `${(ms / 1000).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} s`;

/** v1.7.5: velocidade das telas com usuários reais (médias anônimas dos últimos 7 dias). */
function SpeedCard() {
  const perf = useQuery({ queryKey: ["admin", "perf"], queryFn: () => api.get<PerfRow[]>("/admin/perf"), refetchInterval: 300_000 });
  const rows = perf.data ?? [];
  return (
    <section className="card stack" aria-labelledby="velocidade-das-telas">
      <h2 id="velocidade-das-telas">
        <Gauge size={18} aria-hidden /> Velocidade das telas (7 dias)
      </h2>
      <p className="muted small" style={{ margin: 0 }}>
        Tempo até a tela ficar pronta, medido no aparelho de quem usa. Só médias por tela: não guarda quem abriu, aparelho nem endereço.
        “Lentas” são as aberturas acima de 2,5 s.
      </p>
      {rows.length === 0 ? (
        <p className="muted" style={{ margin: 0 }}>
          Ainda sem medições.
        </p>
      ) : (
        <div className="table-wrap" tabIndex={0} role="region" aria-label="Tabela da velocidade das telas">
          <table className="table table--compact">
            <thead>
              <tr>
                <th>Tela</th>
                <th className="num">Aberturas</th>
                <th className="num">Média</th>
                <th className="num">Pior</th>
                <th className="num">Lentas</th>
                <th className="num">Travada média</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.screen}>
                  <td>{SCREEN_NAMES[row.screen] ?? row.screen}</td>
                  <td className="num">{row.count}</td>
                  <td className={`num ${row.average_ms > 2500 ? "tone--error" : ""}`}>{seconds(row.average_ms)}</td>
                  <td className="num">{seconds(row.max_ms)}</td>
                  <td className="num">{row.slow_pct.toLocaleString("pt-BR")}%</td>
                  <td className="num">{row.frame_ms} ms</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

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
      <SpeedCard />
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
