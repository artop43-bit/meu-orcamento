import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { api, errorMessage } from "../api/client";
import { announce } from "../lib/announce";
import { money, parseMoney, percent } from "../lib/format";
import { rebalance } from "../lib/rebalance";
import { MoneyInput } from "./budget";
import { Alert, Button } from "./ui";

const KEY = ["budget", "investment-targets"] as const;

/**
 * Investimentos › Alocação (v1.4): meta de divisão por classe e quanto do próximo aporte vai
 * para cada uma. Fica recolhido até a pessoa definir uma meta.
 */
export function AllocationTarget({ current, labels }: { current: Record<string, number>; labels: Record<string, string> }) {
  const queryClient = useQueryClient();
  const targets = useQuery({ queryKey: KEY, queryFn: () => api.get<Record<string, number>>("/investments/targets") });
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [contribution, setContribution] = useState("1.000,00");
  const [error, setError] = useState("");
  const saved = targets.data ?? {};
  const hasTargets = Object.keys(saved).length > 0;
  const kinds = [...new Set([...Object.keys(current), ...Object.keys(saved)])];
  const sum = kinds.reduce((s, k) => s + (Number((draft[k] ?? "0").replace(",", ".")) || 0), 0);

  function start() {
    setDraft(Object.fromEntries(kinds.map((k) => [k, saved[k] !== undefined ? String(saved[k]) : ""])));
    setEditing(true);
  }

  async function save() {
    setError("");
    try {
      const body = Object.fromEntries(kinds.map((k) => [k, Number((draft[k] ?? "0").replace(",", ".")) || 0]));
      queryClient.setQueryData(KEY, await api.put<Record<string, number>>("/investments/targets", { targets: body }));
      setEditing(false);
      announce("Meta de alocação salva");
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  if (editing) {
    return (
      <div className="stack stack--tight allocation-target">
        <Alert tone="error">{error}</Alert>
        {kinds.map((k) => (
          <label key={k} className="allocation-target__row">
            <span>{labels[k] ?? k}</span>
            <input inputMode="decimal" value={draft[k] ?? ""} onChange={(e) => setDraft((d) => ({ ...d, [k]: e.target.value }))} placeholder="0" aria-label={`Meta de ${labels[k] ?? k} (%)`} />
            <span className="muted">%</span>
          </label>
        ))}
        <p className={`small ${Math.abs(sum - 100) > 0.5 ? "tone--warn" : "muted"}`} style={{ margin: 0 }} aria-live="polite">
          Soma: {percent(sum)} {Math.abs(sum - 100) > 0.5 && "(precisa dar 100%)"}
        </p>
        <div className="row" style={{ gap: 8 }}>
          <Button type="button" onClick={() => void save()}>
            Salvar meta
          </Button>
          <Button type="button" variant="secondary" onClick={() => setEditing(false)}>
            Cancelar
          </Button>
        </div>
      </div>
    );
  }

  if (!hasTargets) {
    return (
      <button type="button" className="link-btn small" onClick={start} style={{ justifySelf: "start" }}>
        Definir uma meta de alocação
      </button>
    );
  }

  const rows = rebalance(current, saved, Number(parseMoney(contribution) ?? 0)).filter((r) => r.target > 0 || r.now > 0);
  return (
    <div className="stack stack--tight allocation-target">
      <div className="row allocation-target__head">
        <label>
          Próximo aporte
          <MoneyInput value={contribution} onChange={setContribution} required={false} />
        </label>
        <button type="button" className="link-btn small" onClick={start}>
          Ajustar a meta
        </button>
      </div>
      <ul className="items">
        {rows.map((r) => (
          <li key={r.kind} className="item">
            <span className="item__main">
              <span className="item__title">{labels[r.kind] ?? r.kind}</span>
              <span className="item__meta">meta {percent(r.target)}</span>
            </span>
            <strong className="num">{r.add > 0 ? `+ ${money(r.add)}` : "—"}</strong>
          </li>
        ))}
      </ul>
      <p className="muted small" style={{ margin: 0 }}>
        Distribui o aporte para aproximar a carteira da sua meta, sem vender nada. Não é recomendação de investimento.
      </p>
    </div>
  );
}
