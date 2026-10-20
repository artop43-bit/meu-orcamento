import { useQuery } from "@tanstack/react-query";
import { BellRing, CalendarClock, Store, TrendingUp, TriangleAlert } from "lucide-react";

import { sharingApi, type MonthAlert } from "../api/sharing";

const ICONS: Record<MonthAlert["kind"], typeof BellRing> = {
  unusual: TriangleAlert,
  new_merchant: Store,
  price_up: TrendingUp,
  renewal: CalendarClock,
};

/** Orçamento: gastos fora do padrão, lugares novos, assinaturas mais caras e renovações. */
export function MonthAlerts({ month }: { month: string }) {
  const alerts = useQuery({ queryKey: ["budget", "alerts", month], queryFn: () => sharingApi.alerts(month) });
  const list = alerts.data ?? [];
  if (list.length === 0) return null;
  return (
    <section className="card stack month-alerts" aria-labelledby="month-alerts-title">
      <h2 id="month-alerts-title">
        <BellRing size={18} aria-hidden /> Atenção
      </h2>
      <ul className="month-alerts__list">
        {list.map((a) => {
          const Icon = ICONS[a.kind];
          return (
            <li key={a.key} className={`month-alert month-alert--${a.kind}`}>
              <Icon size={16} aria-hidden />
              <span>
                <strong>{a.title}</strong>
                <span className="muted small">{a.text}</span>
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
