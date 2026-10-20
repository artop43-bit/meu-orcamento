import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { PiggyBank, Target } from "lucide-react";
import { Link } from "react-router";

import { budgetApi, keys } from "../api/budget";
import { errorMessage } from "../api/client";
import { fileUrl } from "../api/support";
import { announce } from "../lib/announce";
import { money, percent, thisMonth } from "../lib/format";
import { goalKind, projectionText } from "../lib/goals";
import { Bar } from "./budget";
import { Alert, Button } from "./ui";

const DISMISS_KEY = "sugestao-meta-dispensada";

function dismissedThisMonth(): boolean {
  try {
    return localStorage.getItem(DISMISS_KEY) === thisMonth();
  } catch {
    return false;
  }
}

/**
 * Quadro "Metas" do Orçamento: a meta principal com a projeção em uma linha e, quando o mês
 * tem sobra, a sugestão de aporte (nada é movido sem confirmação).
 */
export function GoalTeaser({ showSuggestion }: { showSuggestion: boolean }) {
  const queryClient = useQueryClient();
  const goals = useQuery({ queryKey: keys.goals, queryFn: budgetApi.goals });
  const suggestion = useQuery({
    queryKey: ["budget", "goals", "suggestion"],
    queryFn: budgetApi.goalSuggestion,
    enabled: showSuggestion,
  });
  const [dismissed, setDismissed] = useState(dismissedThisMonth);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const active = (goals.data ?? []).filter((g) => !g.completed_at);
  const goal = active.find((g) => g.is_main) ?? active[0];
  if (!goals.data) return null;
  if (!goal)
    return (
      <section className="card stack stack--tight">
        <h2>
          <Target size={18} aria-hidden /> Metas
        </h2>
        <p className="muted small" style={{ margin: 0 }}>
          Defina um objetivo e acompanhe aqui o progresso e a data prevista de conclusão.
        </p>
        <div>
          <Link className="btn btn--secondary" to="/metas">
            Criar meta
          </Link>
        </div>
      </section>
    );

  const info = goalKind(goal.kind);
  const projection = projectionText(goal);
  const tip = suggestion.data && suggestion.data.goal_id === goal.id && !dismissed ? suggestion.data : null;

  async function save() {
    if (!tip) return;
    setBusy(true);
    setError("");
    try {
      await budgetApi.contribute(goal!.id, tip.amount);
      announce(`${money(tip.amount)} guardados em ${goal!.name}`);
      await queryClient.invalidateQueries({ queryKey: ["budget"] });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function later() {
    try {
      localStorage.setItem(DISMISS_KEY, thisMonth());
    } catch {
      // sem armazenamento: some só nesta visita
    }
    setDismissed(true);
  }

  return (
    <section className="card stack goal-teaser" aria-labelledby="goal-teaser-title">
      <div className="section-header">
        <h2 id="goal-teaser-title">
          <Target size={18} aria-hidden /> Meta principal
        </h2>
        <Link to="/metas" className="small">
          Ver metas
        </Link>
      </div>
      <div className="goal-teaser__head">
        {goal.image_id ? (
          <img className="goal-teaser__image" src={fileUrl(goal.image_id)} alt="" loading="lazy" />
        ) : (
          <span className="kpi__icon" aria-hidden>
            {info.icon}
          </span>
        )}
        <span className="goal-teaser__name">
          <strong>{goal.name}</strong>
          <span className="muted small">
            {money(goal.current_amount)} de {money(goal.target_amount)} · {percent(goal.progress_pct)}
          </span>
        </span>
      </div>
      <Bar pct={goal.progress_pct} />
      {projection.text && <p className={`goal-status goal-status--${projection.tone}`}>{projection.text}</p>}
      {tip && (
        <div className="goal-suggestion" role="region" aria-label="Sugestão de aporte">
          <PiggyBank size={18} aria-hidden />
          <p>
            Sobra prevista de <strong>{money(tip.surplus)}</strong> neste mês. Destinar <strong>{money(tip.amount)}</strong> à meta{" "}
            <em>{tip.goal_name}</em>?
          </p>
          <Alert tone="error">{error}</Alert>
          <div className="goal-suggestion__actions">
            <Button type="button" loading={busy} onClick={() => void save()}>
              Guardar {money(tip.amount)}
            </Button>
            <Button type="button" variant="secondary" onClick={later}>
              Agora não
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}
