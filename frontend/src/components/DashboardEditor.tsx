import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp } from "lucide-react";

import { ME_KEY, type User } from "../api/auth";
import { errorMessage } from "../api/client";
import { inboxApi } from "../api/inbox";
import { announce } from "../lib/announce";
import { areaOf, labelOf, move, readDashboard, type DashboardArea, type DashboardCard } from "../lib/dashboard";
import { Alert, Button } from "./ui";

const AREAS: { area: DashboardArea; title: string; hint: string }[] = [
  { area: "top", title: "No topo", hint: "Acima da lista de despesas." },
  { area: "side", title: "Ao lado da lista", hint: "No celular, aparecem abaixo da lista de despesas." },
];

/** Orçamento › Personalizar o painel: quais cartões aparecem e em que ordem (salvo na conta). */
export function DashboardEditor({ saved, onDone }: { saved: string | null | undefined; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [cards, setCards] = useState<DashboardCard[]>(() => readDashboard(saved));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function save(next: DashboardCard[] | null) {
    setBusy(true);
    setError("");
    try {
      const out = await inboxApi.dashboard(next);
      queryClient.setQueryData<User | null>(ME_KEY, (me) => (me ? { ...me, dashboard: out.dashboard } : me));
      announce(next ? "Painel salvo" : "Painel restaurado ao padrão");
      onDone();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack dashboard-editor">
      <Alert tone="error">{error}</Alert>
      {AREAS.map(({ area, title, hint }) => {
        const list = cards.filter((c) => areaOf(c.key) === area);
        return (
          <fieldset key={area} className="radios">
            <legend className="field-label">{title}</legend>
            <p className="muted small" style={{ margin: "0 0 6px" }}>
              {hint}
            </p>
            <ul className="dashboard-editor__list">
              {list.map((card, index) => (
                <li key={card.key}>
                  <label className="check">
                    <input
                      type="checkbox"
                      checked={card.visible}
                      onChange={(e) => setCards((all) => all.map((c) => (c.key === card.key ? { ...c, visible: e.target.checked } : c)))}
                    />
                    {labelOf(card.key)}
                  </label>
                  <span className="dashboard-editor__moves">
                    <button
                      type="button"
                      className="icon-btn"
                      aria-label={`Subir ${labelOf(card.key)}`}
                      disabled={index === 0}
                      onClick={() => setCards((all) => move(all, card.key, -1))}
                    >
                      <ArrowUp size={16} aria-hidden />
                    </button>
                    <button
                      type="button"
                      className="icon-btn"
                      aria-label={`Descer ${labelOf(card.key)}`}
                      disabled={index === list.length - 1}
                      onClick={() => setCards((all) => move(all, card.key, 1))}
                    >
                      <ArrowDown size={16} aria-hidden />
                    </button>
                  </span>
                </li>
              ))}
            </ul>
          </fieldset>
        );
      })}
      <p className="muted small" style={{ margin: 0 }}>
        A lista de despesas fica sempre no painel. O plano para equilibrar o mês aparece sozinho quando o mês fica no negativo.
      </p>
      <div className="row" style={{ justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
        <Button type="button" variant="secondary" onClick={() => void save(null)} disabled={busy}>
          Restaurar padrão
        </Button>
        <Button type="button" loading={busy} onClick={() => void save(cards)}>
          Salvar painel
        </Button>
      </div>
    </div>
  );
}
