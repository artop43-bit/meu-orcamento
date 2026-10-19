import { useQuery } from "@tanstack/react-query";
import { maskMoney } from "../lib/format";
import {
  ChevronRight,
  CircleAlert,
  Info,
  Sparkles,
  ThumbsUp,
  TrendingDown,
  TriangleAlert,
  Trophy,
  type LucideIcon,
} from "lucide-react";
import { Link } from "react-router";

import { insightsApi, type InsightMessage, type InsightTone, type Insights } from "../api/insights";

export const insightsKey = (month: string) => ["budget", "insights", month] as const;

export function useInsights(month: string) {
  return useQuery({ queryKey: insightsKey(month), queryFn: () => insightsApi.insights(month) });
}

const MOOD: Record<Insights["mood"], { icon: LucideIcon; className: string }> = {
  great: { icon: Trophy, className: "mood--great" },
  good: { icon: ThumbsUp, className: "mood--good" },
  attention: { icon: TriangleAlert, className: "mood--attention" },
  concern: { icon: TrendingDown, className: "mood--concern" },
  empty: { icon: Sparkles, className: "mood--empty" },
};

const TONE: Record<InsightTone, { icon: LucideIcon; label: string }> = {
  praise: { icon: ThumbsUp, label: "Elogio" },
  info: { icon: Info, label: "Dica" },
  warning: { icon: TriangleAlert, label: "Atenção" },
  danger: { icon: CircleAlert, label: "Importante" },
};

function MessageItem({ message }: { message: InsightMessage }) {
  const { icon: Icon, label } = TONE[message.tone];
  return (
    <li className={`insight insight--${message.tone}`}>
      <span className="insight__icon" aria-hidden>
        <Icon size={18} />
      </span>
      <span>
        <span className="sr-only">{label}: </span>
        <strong className="insight__title">{maskMoney(message.title)}</strong>
        <span className="insight__text">{maskMoney(message.text)}</span>
      </span>
    </li>
  );
}

/** Leitura do mês feita pelo "consultor": título, resumo e observações. */
export function ConsultantCard({ data }: { data: Insights }) {
  const { icon: Icon, className } = MOOD[data.mood];
  return (
    <section className={`card consultant ${className}`} aria-labelledby="consultor-titulo">
      <div className="consultant__head">
        <span className="consultant__icon" aria-hidden>
          <Icon size={26} />
        </span>
        <div>
          <p className="consultant__eyebrow">Seu consultor</p>
          <h2 id="consultor-titulo">{data.headline}</h2>
        </div>
      </div>
      <p className="consultant__summary">{maskMoney(data.summary)}</p>
      {data.messages.length > 0 && (
        <ul className="insights" aria-label="Observações do mês">
          {data.messages.map((m) => (
            <MessageItem key={m.title} message={m} />
          ))}
        </ul>
      )}
    </section>
  );
}

/** Alertas: o que precisa de ação (limites, atrasos, metas, próximo mês). */
export function AlertsCard({ alerts }: { alerts: InsightMessage[] }) {
  return (
    <section className="card stack" aria-labelledby="alertas-titulo">
      <h2 id="alertas-titulo">
        Alertas{" "}
        {alerts.length > 0 && <span className="badge badge--warn">{alerts.length}</span>}
      </h2>
      {alerts.length === 0 ? (
        <p className="muted">Nenhum alerta no momento. Tudo dentro do esperado.</p>
      ) : (
        <ul className="insights">
          {alerts.map((a) => (
            <MessageItem key={a.title} message={a} />
          ))}
        </ul>
      )}
    </section>
  );
}

/** Resumo do consultor na tela do Orçamento, com atalho para a análise completa. */
export function ConsultantTeaser({ month }: { month: string }) {
  const insights = useInsights(month);
  const data = insights.data;
  if (!data || data.mood === "empty") return null;
  const { icon: Icon, className } = MOOD[data.mood];
  const urgent = data.alerts.filter((a) => a.tone === "danger" || a.tone === "warning");
  return (
    <Link to={`/analises?mes=${month}`} className={`teaser ${className}`}>
      <span className="consultant__icon" aria-hidden>
        <Icon size={20} />
      </span>
      <span className="grow">
        <strong>{data.headline}</strong>
        <span className="teaser__text">
          {urgent.length > 0 ? `${maskMoney(urgent[0].title)}${urgent.length > 1 ? ` e mais ${urgent.length - 1} alerta(s)` : ""}` : "Veja a análise completa do mês"}
        </span>
      </span>
      <ChevronRight size={18} aria-hidden />
    </Link>
  );
}
