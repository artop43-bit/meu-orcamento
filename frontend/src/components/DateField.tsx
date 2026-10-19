import { useEffect, useId, useRef, useState, type InputHTMLAttributes } from "react";
import { CalendarDays } from "lucide-react";

/**
 * Campos de data do app: sempre dd/mm/aaaa (ou mm/aaaa), iguais em qualquer navegador.
 * Digitação com máscara + botão que abre o calendário do sistema. O valor trafega em ISO
 * ("2026-10-19" / "2026-10"). Anos aceitos: 2000 a 2100 (o servidor confere de novo).
 */
export const MIN_YEAR = 2000;
export const MAX_YEAR = 2100;
export const DATE_ERROR = `Data inválida: use dd/mm/aaaa com ano entre ${MIN_YEAR} e ${MAX_YEAR}.`;

function isoToText(iso: string, month: boolean): string {
  if (!iso) return "";
  const [y, m, d] = iso.split("-");
  return month ? `${m}/${y}` : `${d}/${m}/${y}`;
}

/** "19102026" ou "19/10/2026" → "2026-10-19"; null se inválida. */
export function textToIso(text: string, month: boolean): string | null {
  const digits = text.replace(/\D/g, "");
  if (month) {
    if (digits.length !== 6) return null;
    const m = Number(digits.slice(0, 2));
    const y = Number(digits.slice(2));
    if (m < 1 || m > 12 || y < MIN_YEAR || y > MAX_YEAR) return null;
    return `${y}-${String(m).padStart(2, "0")}`;
  }
  if (digits.length !== 8) return null;
  const d = Number(digits.slice(0, 2));
  const m = Number(digits.slice(2, 4));
  const y = Number(digits.slice(4));
  if (y < MIN_YEAR || y > MAX_YEAR || m < 1 || m > 12) return null;
  const last = new Date(y, m, 0).getDate();
  if (d < 1 || d > last) return null;
  return `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}

function mask(text: string, month: boolean): string {
  const digits = text.replace(/\D/g, "").slice(0, month ? 6 : 8);
  if (month) return digits.length > 2 ? `${digits.slice(0, 2)}/${digits.slice(2)}` : digits;
  if (digits.length > 4) return `${digits.slice(0, 2)}/${digits.slice(2, 4)}/${digits.slice(4)}`;
  if (digits.length > 2) return `${digits.slice(0, 2)}/${digits.slice(2)}`;
  return digits;
}

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "onChange" | "type" | "min" | "max"> & {
  value: string;
  onChange: (iso: string) => void;
  /** Só mês e ano (mm/aaaa). */
  month?: boolean;
  min?: string;
  max?: string;
  label?: string;
};

export function DateField({ value, onChange, month = false, min, max, label, required, id, ...rest }: Props) {
  const [text, setText] = useState(() => isoToText(value, month));
  const [invalid, setInvalid] = useState(false);
  const picker = useRef<HTMLInputElement>(null);
  const autoId = useId();
  const fieldId = id ?? autoId;

  // Valor mudou de fora (ex.: limpar o formulário): atualiza o texto.
  useEffect(() => {
    if ((textToIso(text, month) ?? "") !== value) setText(isoToText(value, month));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, month]);

  function commit(next: string) {
    const masked = mask(next, month);
    setText(masked);
    if (!masked) {
      setInvalid(false);
      onChange("");
      return;
    }
    const iso = textToIso(masked, month);
    const outOfRange = iso !== null && ((min && iso < min) || (max && iso > max));
    const complete = masked.replace(/\D/g, "").length === (month ? 6 : 8);
    setInvalid(complete && (iso === null || !!outOfRange));
    if (iso && !outOfRange) onChange(iso);
  }

  function openPicker() {
    const el = picker.current;
    if (!el) return;
    try {
      el.showPicker();
    } catch {
      el.focus();
    }
  }

  return (
    <span className={`date-field ${invalid ? "is-invalid" : ""}`}>
      <input
        {...rest}
        id={fieldId}
        aria-label={label}
        type="text"
        inputMode="numeric"
        autoComplete="off"
        placeholder={month ? "mm/aaaa" : "dd/mm/aaaa"}
        maxLength={month ? 7 : 10}
        value={text}
        required={required}
        aria-invalid={invalid || undefined}
        aria-describedby={invalid ? `${fieldId}-erro` : undefined}
        onChange={(e) => commit(e.target.value)}
      />
      <button type="button" className="date-field__btn" onClick={openPicker} aria-label="Abrir calendário" tabIndex={-1}>
        <CalendarDays size={17} aria-hidden />
      </button>
      {/* Calendário nativo, invisível: só fornece o seletor. */}
      <input
        ref={picker}
        className="date-field__native"
        type={month ? "month" : "date"}
        tabIndex={-1}
        aria-hidden
        min={min ?? (month ? `${MIN_YEAR}-01` : `${MIN_YEAR}-01-01`)}
        max={max ?? (month ? `${MAX_YEAR}-12` : `${MAX_YEAR}-12-31`)}
        value={value}
        onChange={(e) => e.target.value && commit(isoToText(e.target.value, month))}
      />
      {invalid && (
        <small id={`${fieldId}-erro`} className="date-field__error" role="alert">
          {DATE_ERROR}
        </small>
      )}
    </span>
  );
}
