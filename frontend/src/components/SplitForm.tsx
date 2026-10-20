import { useEffect, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, X } from "lucide-react";
import { Link } from "react-router";

import { errorMessage } from "../api/client";
import { SPLITS_KEY, sharingApi, type SplitMode } from "../api/sharing";
import { announce } from "../lib/announce";
import { money, parseMoney } from "../lib/format";
import { Alert, Button } from "./ui";

type Row = { person: string; value: string };

/** Dividir uma despesa que você pagou: cada pessoa fica devendo a parte dela. */
export function SplitForm({ expense, onDone }: { expense: { id: string; description: string; amount: string }; onDone: () => void }) {
  const queryClient = useQueryClient();
  const board = useQuery({ queryKey: SPLITS_KEY, queryFn: sharingApi.board });
  const existing = useQuery({ queryKey: [...SPLITS_KEY, "expense", expense.id], queryFn: () => sharingApi.expenseSplit(expense.id) });
  const [mode, setMode] = useState<SplitMode>("equal");
  const [includeMe, setIncludeMe] = useState(true);
  const [rows, setRows] = useState<Row[]>([{ person: "", value: "" }]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const total = Number(expense.amount);

  // Divisão já feita: carrega as pessoas para editar.
  useEffect(() => {
    const open = (existing.data ?? []).filter((s) => !s.settled_at);
    if (open.length) setRows(open.map((s) => ({ person: s.person, value: "" })));
  }, [existing.data]);

  const filled = rows.filter((r) => r.person.trim());
  const parts = filled.map((r) => {
    if (mode === "equal") return total / (filled.length + (includeMe ? 1 : 0) || 1);
    if (mode === "percent") return (total * Number(r.value.replace(",", ".") || 0)) / 100;
    return Number(parseMoney(r.value) ?? 0);
  });
  const others = parts.reduce((a, b) => a + b, 0);
  const mine = total - others;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      await sharingApi.split(expense.id, {
        mode,
        include_me: includeMe,
        people: filled.map((r) => ({
          person: r.person.trim(),
          value: mode === "equal" ? undefined : mode === "percent" ? r.value.replace(",", ".") : (parseMoney(r.value) ?? "0"),
        })),
      });
      announce("Despesa dividida");
      await queryClient.invalidateQueries({ queryKey: SPLITS_KEY });
      onDone();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="inline-form" onSubmit={submit}>
      <p className="muted small" style={{ margin: 0 }}>
        <strong>{expense.description}</strong> · {money(expense.amount)}. Quem está na divisão fica devendo a parte dela a você; o placar fica em{" "}
        <Link to="/divisoes">Divisões</Link>.
      </p>
      <Alert tone="error">{error}</Alert>
      <fieldset className="radios">
        <legend className="field-label">Como dividir</legend>
        <div className="segmented">
          {(
            [
              ["equal", "Partes iguais"],
              ["amount", "Por valor"],
              ["percent", "Por porcentagem"],
            ] as const
          ).map(([value, label]) => (
            <label key={value}>
              <input type="radio" name="split-mode" checked={mode === value} onChange={() => setMode(value)} />
              {label}
            </label>
          ))}
        </div>
      </fieldset>
      {mode === "equal" && (
        <label className="check">
          <input type="checkbox" checked={includeMe} onChange={(e) => setIncludeMe(e.target.checked)} />
          Incluir a minha parte na divisão
        </label>
      )}
      <datalist id="split-people">
        {(board.data?.names ?? []).map((n) => (
          <option key={n} value={n} />
        ))}
      </datalist>
      <ul className="split-rows">
        {rows.map((row, i) => (
          <li key={i} className="split-row">
            <label>
              <span className="sr-only">Pessoa {i + 1}</span>
              <input
                value={row.person}
                list="split-people"
                placeholder="Nome da pessoa"
                aria-label={`Nome da pessoa ${i + 1}`}
                maxLength={60}
                onChange={(e) => setRows(rows.map((r, j) => (j === i ? { ...r, person: e.target.value } : r)))}
              />
            </label>
            {mode !== "equal" && (
              <label>
                <span className="sr-only">{mode === "percent" ? `Porcentagem da pessoa ${i + 1}` : `Valor da pessoa ${i + 1}`}</span>
                <input
                  value={row.value}
                  inputMode="decimal"
                  placeholder={mode === "percent" ? "%" : "0,00"}
                  aria-label={mode === "percent" ? `Porcentagem da pessoa ${i + 1}` : `Valor da pessoa ${i + 1}`}
                  onChange={(e) => setRows(rows.map((r, j) => (j === i ? { ...r, value: e.target.value.replace(/[^\d,.]/g, "") } : r)))}
                />
              </label>
            )}
            <span className="split-row__part num">{row.person.trim() ? money(parts[filled.indexOf(row)] ?? 0) : "—"}</span>
            {rows.length > 1 && (
              <button type="button" className="icon-btn" aria-label={`Remover pessoa ${i + 1}`} onClick={() => setRows(rows.filter((_, j) => j !== i))}>
                <X size={16} />
              </button>
            )}
          </li>
        ))}
      </ul>
      <div>
        <Button type="button" variant="secondary" onClick={() => setRows([...rows, { person: "", value: "" }])}>
          <Plus size={16} /> Adicionar pessoa
        </Button>
      </div>
      <p className="summary-box" aria-live="polite">
        Os outros devem <strong>{money(others)}</strong>; a sua parte fica em <strong>{money(Math.max(0, mine))}</strong>.
      </p>
      <div className="form-actions">
        <Button type="button" variant="secondary" onClick={onDone}>
          Cancelar
        </Button>
        <Button type="submit" loading={busy} disabled={filled.length === 0 || mine < -0.005}>
          Dividir
        </Button>
      </div>
    </form>
  );
}
