import type { ReactNode } from "react";

import type { Category } from "../api/budget";
import { parseMoney } from "../lib/format";
import { Button } from "./ui";
import { maybeCountUp } from "./CountUp";

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "accent" | "warn" }) {
  return <span className={`badge badge--${tone}`}>{children}</span>;
}

export function Stat({ label, value, tone }: { label: string; value: string; tone?: "ok" | "error" }) {
  return (
    <div className="stat">
      <span className="stat__label">{label}</span>
      <strong className={tone ? `stat__value tone--${tone}` : "stat__value"}>{maybeCountUp(value)}</strong>
    </div>
  );
}

/** Barra horizontal proporcional (0–100). */
export function Bar({ pct, color }: { pct: number; color?: string }) {
  const width = Math.max(0, Math.min(100, pct));
  return (
    <div className="bar">
      <div className="bar__fill" style={{ width: `${width}%`, background: color }} />
    </div>
  );
}

export function CategorySelect({
  categories,
  value,
  onChange,
  id,
  label,
}: {
  categories: Category[];
  value: string;
  onChange: (value: string) => void;
  id?: string;
  /** Nome para leitores de tela quando não há <label> visível. */
  label?: string;
}) {
  return (
    <select id={id} value={value} onChange={(e) => onChange(e.target.value)} aria-label={label}>
      <option value="">Sem categoria</option>
      {categories.map((c) => (
        <option key={c.id} value={c.id}>
          {c.name}
        </option>
      ))}
    </select>
  );
}

/** Campo de valor em reais que aceita "1.234,56", "1234.56" etc. */
export function MoneyInput({
  value,
  onChange,
  id,
  placeholder = "0,00",
  label,
  required = true,
}: {
  value: string;
  onChange: (value: string) => void;
  id?: string;
  placeholder?: string;
  required?: boolean;
  /** Nome para leitores de tela quando não há <label> visível. */
  label?: string;
}) {
  return (
    <input
      id={id}
      aria-label={label}
      inputMode="decimal"
      placeholder={placeholder}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      required={required}
    />
  );
}

/** Valida o valor digitado; devolve o texto para a API ou lança erro amigável. */
export function requireMoney(input: string): string {
  const parsed = parseMoney(input);
  if (!parsed || Number(parsed) <= 0) throw new Error("Informe um valor válido, maior que zero.");
  return parsed;
}

export function FormActions({ loading, onCancel, label = "Salvar" }: { loading: boolean; onCancel: () => void; label?: string }) {
  return (
    <div className="form-actions">
      <Button type="button" variant="secondary" onClick={onCancel}>
        Cancelar
      </Button>
      <Button type="submit" loading={loading}>
        {label}
      </Button>
    </div>
  );
}
