import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { BellRing, ChevronDown, ListChecks } from "lucide-react";
import { Link } from "react-router";

import { sharingApi } from "../api/sharing";
import { maskMoney } from "../lib/format";
import { ConsultantTeaser, useInsights } from "./consultant";
import { MonthAlerts } from "./MonthAlerts";
import { RecoveryCard } from "./RecoveryPlan";

const KEY = "avisos-do-mes-abertos";

function readOpen(): boolean {
  try {
    return localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

/**
 * Painel do Orçamento (v1.7): desempenho do mês, plano para equilibrar, alertas do mês e
 * lançamentos para revisar reunidos numa faixa só, que abre ao tocar. A faixa mostra quantos
 * avisos há e o título de cada um, para dar para decidir sem abrir.
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
  const insights = useInsights(month);
  const monthAlerts = useQuery({ queryKey: ["budget", "alerts", month], queryFn: () => sharingApi.alerts(month), enabled: alerts });

  const titles: string[] = [];
  const mood = insights.data?.mood;
  const showConsultant = consultant && !!insights.data && mood !== "empty";
  if (showConsultant) titles.push(maskMoney(insights.data!.headline));
  if (negative) titles.push("Plano para equilibrar o mês");
  const alertList = alerts ? (monthAlerts.data ?? []) : [];
  if (alertList.length === 1) titles.push(maskMoney(alertList[0]!.title));
  else if (alertList.length > 1) titles.push(`${alertList.length} alertas do mês`);
  if (reviewCount > 0) titles.push(`${reviewCount} para revisar`);
  const count = (showConsultant ? 1 : 0) + (negative ? 1 : 0) + alertList.length + (reviewCount > 0 ? 1 : 0);
  if (count === 0) return null;
  const urgent = negative || mood === "concern" || (insights.data?.alerts ?? []).some((a) => a.tone === "danger");

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
        {showConsultant && <ConsultantTeaser month={month} />}
        {negative && <RecoveryCard month={month} />}
        {alerts && <MonthAlerts month={month} />}
        {reviewCount > 0 && (
          <Link to="/revisar" className="review-banner">
            <ListChecks size={18} aria-hidden />
            <span>
              <strong>{reviewCount} despesa(s) importada(s) para revisar.</strong> Confira as categorias antes que entrem nas análises.
            </span>
          </Link>
        )}
      </div>
    </section>
  );
}
