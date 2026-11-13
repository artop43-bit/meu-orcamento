import { useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  BellRing,
  CalendarClock,
  ChevronDown,
  ChevronRight,
  HandCoins,
  HeartHandshake,
  ListChecks,
  Store,
  ThumbsUp,
  TrendingDown,
  TrendingUp,
  TriangleAlert,
  Trophy,
  type LucideIcon,
} from "lucide-react";
import { Link } from "react-router";

import { sharingApi, type MonthAlert } from "../api/sharing";
import { maskMoney, monthLabel } from "../lib/format";
import { useInsights } from "./consultant";
import { RecoveryPlan } from "./RecoveryPlan";
import { Sheet } from "./ui";

const KEY = "avisos-do-mes-abertos";

type Tone = "danger" | "warn" | "info";

const ALERT_ICONS: Record<MonthAlert["kind"], LucideIcon> = {
  unusual: TriangleAlert,
  new_merchant: Store,
  price_up: TrendingUp,
  renewal: CalendarClock,
  loan_late: HandCoins,
};

const MOOD: Record<string, { icon: LucideIcon; tone: Tone }> = {
  great: { icon: Trophy, tone: "info" },
  good: { icon: ThumbsUp, tone: "info" },
  attention: { icon: TriangleAlert, tone: "warn" },
  concern: { icon: TrendingDown, tone: "danger" },
};

function readOpen(): boolean {
  try {
    return localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

/**
 * Linha de aviso (v1.7.5): todo aviso do Orçamento tem o mesmo formato — traço lateral na cor do
 * tom, ícone, título e texto. Com `to` ou `onClick` a linha inteira é clicável e ganha a seta;
 * sem ação ela só informa (sem seta e sem reagir ao mouse).
 */
export function NoticeRow({
  tone,
  icon: Icon,
  title,
  text,
  to,
  onClick,
  name,
}: {
  tone: Tone;
  icon: LucideIcon;
  title: ReactNode;
  text?: ReactNode;
  to?: string;
  onClick?: () => void;
  name?: string;
}) {
  const body = (
    <>
      <span className="notice-row__icon" aria-hidden>
        <Icon size={18} />
      </span>
      <span className="notice-row__body">
        <strong>{title}</strong>
        {text && <span className="notice-row__text">{text}</span>}
      </span>
      {(to || onClick) && <ChevronRight size={18} className="notice-row__arrow" aria-hidden />}
    </>
  );
  const className = `notice-row notice-row--${tone}`;
  if (to)
    return (
      <Link to={to} className={className} data-notice={name}>
        {body}
      </Link>
    );
  if (onClick)
    return (
      <button type="button" className={className} onClick={onClick} data-notice={name}>
        {body}
      </button>
    );
  return (
    <div className={className} data-notice={name}>
      {body}
    </div>
  );
}

/**
 * Painel do Orçamento: desempenho do mês, plano para equilibrar, alertas do mês e lançamentos
 * para revisar reunidos numa faixa só, que abre ao tocar. A faixa mostra quantos avisos há e o
 * título de cada um, para dar para decidir sem abrir.
 */
export function MonthNotices({
  month,
  consultant,
  alerts,
  negative,
  reviewCount,
}: {
  month: string;
  consultant: boolean;
  alerts: boolean;
  negative: boolean;
  reviewCount: number;
}) {
  const [open, setOpen] = useState(readOpen);
  const [plan, setPlan] = useState(false);
  const insights = useInsights(month);
  const monthAlerts = useQuery({ queryKey: ["budget", "alerts", month], queryFn: () => sharingApi.alerts(month), enabled: alerts });

  const titles: string[] = [];
  const data = insights.data;
  const mood = data?.mood;
  const showConsultant = consultant && !!data && mood !== "empty";
  if (showConsultant) titles.push(maskMoney(data!.headline));
  if (negative) titles.push("Plano para equilibrar o mês");
  const alertList = alerts ? (monthAlerts.data ?? []) : [];
  if (alertList.length === 1) titles.push(maskMoney(alertList[0]!.title));
  else if (alertList.length > 1) titles.push(`${alertList.length} alertas do mês`);
  if (reviewCount > 0) titles.push(`${reviewCount} para revisar`);
  const count = (showConsultant ? 1 : 0) + (negative ? 1 : 0) + alertList.length + (reviewCount > 0 ? 1 : 0);
  if (count === 0) return null;
  const urgentAlerts = (data?.alerts ?? []).filter((a) => a.tone === "danger" || a.tone === "warning");
  const urgent = negative || mood === "concern" || (data?.alerts ?? []).some((a) => a.tone === "danger");

  function toggle() {
    const next = !open;
    setOpen(next);
    try {
      localStorage.setItem(KEY, next ? "1" : "0");
    } catch {
      /* sem armazenamento: só não lembra */
    }
  }

  return (
    <section className={`notices ${open ? "is-open" : ""} ${urgent ? "notices--urgent" : ""}`} aria-label="Avisos do mês">
      <button type="button" className="notices__bar" aria-expanded={open} aria-controls="notices-body" onClick={toggle}>
        <span className="notices__count" aria-hidden>
          {count}
        </span>
        <span className="notices__label">{count === 1 ? "aviso do mês" : "avisos do mês"}</span>
        <span className="notices__preview">{titles.join(" · ")}</span>
        <BellRing size={16} className="notices__bell" aria-hidden />
        <ChevronDown size={18} className="notices__chevron" aria-hidden />
      </button>
      <div className="notices__body" id="notices-body" hidden={!open}>
        {showConsultant && (
          <NoticeRow
            name="consultant"
            tone={MOOD[mood!]?.tone ?? "info"}
            icon={MOOD[mood!]?.icon ?? ThumbsUp}
            title={maskMoney(data!.headline)}
            text={
              urgentAlerts.length > 0
                ? `${maskMoney(urgentAlerts[0]!.title)}${urgentAlerts.length > 1 ? ` e mais ${urgentAlerts.length - 1} alerta(s)` : ""}`
                : "Ver a análise completa"
            }
            to={`/analises?mes=${month}`}
          />
        )}
        {negative && (
          <NoticeRow
            name="recovery"
            tone="info"
            icon={HeartHandshake}
            title="Plano para equilibrar o mês"
            text="Acontece. Veja em poucos passos quanto falta, em quanto tempo dá para cobrir e onde ajustar."
            onClick={() => setPlan(true)}
          />
        )}
        {alertList.length > 0 && (
          <div className="month-alerts notices__group" role="group" aria-label="Alertas do mês">
            {alertList.map((a) => (
              <NoticeRow key={a.key} name="alert" tone="warn" icon={ALERT_ICONS[a.kind]} title={maskMoney(a.title)} text={maskMoney(a.text)} />
            ))}
          </div>
        )}
        {reviewCount > 0 && (
          <NoticeRow
            name="review"
            tone="info"
            icon={ListChecks}
            title={`${reviewCount} despesa(s) importada(s) para revisar`}
            text="Confira as categorias antes que entrem nas análises."
            to="/revisar"
          />
        )}
      </div>
      <Sheet open={plan} title={`Plano para ${monthLabel(month).toLowerCase()}`} onClose={() => setPlan(false)}>
        {plan && <RecoveryPlan month={month} />}
      </Sheet>
    </section>
  );
}
