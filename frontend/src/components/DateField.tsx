import { useEffect, useId, useLayoutEffect, useRef, useState, type InputHTMLAttributes } from "react";
import { CalendarDays } from "lucide-react";

/**
 * Campos de data do app: sempre dd/mm/aaaa (ou mm/aaaa), iguais em qualquer navegador.
 * Digitação com máscara + botão que abre o calendário do sistema. O valor trafega em ISO
 * ("2026-10-19" / "2026-10"). Anos aceitos: 2000 a 2100 (o servidor confere de novo).
 *
 * Data com problema fica marcada com a explicação exata (ex.: "Fevereiro de 2027 tem 28
 * dias.") e IMPEDE o envio do formulário (validação nativa com setCustomValidity).
 */
export const MIN_YEAR = 2000;
export const MAX_YEAR = 2100;

const MONTHS = [
  "Janeiro",
  "Fevereiro",
  "Março",
  "Abril",
  "Maio",
  "Junho",
  "Julho",
  "Agosto",
  "Setembro",
  "Outubro",
  "Novembro",
  "Dezembro",
];

export function daysInMonth(year: number, month: number): number {
  return new Date(year, month, 0).getDate();
}

function isoToText(iso: string, month: boolean): string {
  if (!iso) return "";
  const [y, m, d] = iso.split("-");
  return month ? `${m}/${y}` : `${d}/${m}/${y}`;
}

/**
 * Explica o que há de errado com a data digitada; null se está boa (ou vazia).
 * Com `partial`, data ainda incompleta não é erro (a pessoa está digitando).
 */
export function dateProblem(text: string, month: boolean, opts: { min?: string; max?: string; partial?: boolean } = {}): string | null {
  const digits = text.replace(/\D/g, "");
  if (!digits) return null;
  const size = month ? 6 : 8;
  if (digits.length < size) return opts.partial ? null : `Data incompleta: use ${month ? "mm/aaaa" : "dd/mm/aaaa"}.`;
  const d = month ? 1 : Number(digits.slice(0, 2));
  const m = Number(digits.slice(month ? 0 : 2, month ? 2 : 4));
  const y = Number(digits.slice(month ? 2 : 4));
  if (m < 1 || m > 12) return "Mês inválido: use de 01 a 12.";
  if (y < MIN_YEAR || y > MAX_YEAR) return `Ano inválido: use um ano entre ${MIN_YEAR} e ${MAX_YEAR}.`;
  if (!month) {
    const last = daysInMonth(y, m);
    if (d < 1) return "Dia inválido: use a partir de 01.";
    if (d > last) return `${MONTHS[m - 1]} de ${y} tem ${last} dias.`;
  }
  const iso = month ? `${y}-${String(m).padStart(2, "0")}` : `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
  if (opts.min && iso < opts.min) return `Use uma data a partir de ${isoToText(opts.min, month)}.`;
  if (opts.max && iso > opts.max) return `Use uma data até ${isoToText(opts.max, month)}.`;
  return null;
}

/** "19102026" ou "19/10/2026" → "2026-10-19"; null se inválida. */
export function textToIso(text: string, month: boolean): string | null {
  const digits = text.replace(/\D/g, "");
  if (digits.length !== (month ? 6 : 8) || dateProblem(text, month)) return null;
  return month ? `${digits.slice(2)}-${digits.slice(0, 2)}` : `${digits.slice(4)}-${digits.slice(2, 4)}-${digits.slice(0, 2)}`;
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
  // Erro de data incompleta só aparece depois de sair do campo (ou ao tentar salvar).
  const [touched, setTouched] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const picker = useRef<HTMLInputElement>(null);
  const autoId = useId();
  const fieldId = id ?? autoId;

  // Valor mudou de fora (ex.: limpar o formulário): atualiza o texto.
  useEffect(() => {
    if ((textToIso(text, month) ?? "") !== value) setText(isoToText(value, month));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, month]);

  const problem = dateProblem(text, month, { min, max, partial: !touched });
  const blocking = dateProblem(text, month, { min, max });
  const missing = required && !text;
  const shown = problem ?? (touched && missing ? "Informe a data." : null);

  // A validação nativa do formulário passa a conhecer o erro: o botão salvar não envia.
  useLayoutEffect(() => {
    input.current?.setCustomValidity(blocking ?? "");
  }, [blocking]);

  function commit(next: string) {
    const masked = mask(next, month);
    setText(masked);
    if (!masked) {
      onChange("");
      return;
    }
    const iso = textToIso(masked, month);
    if (iso && !dateProblem(masked, month, { min, max })) onChange(iso);
    else if (masked.replace(/\D/g, "").length === (month ? 6 : 8)) onChange("");
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
    <span className={`date-field ${shown ? "is-invalid" : ""}`}>
      <input
        {...rest}
        ref={input}
        id={fieldId}
        aria-label={label}
        type="text"
        inputMode="numeric"
        autoComplete="off"
        placeholder={month ? "mm/aaaa" : "dd/mm/aaaa"}
        maxLength={month ? 7 : 10}
        value={text}
        required={required}
        aria-invalid={shown ? true : undefined}
        aria-describedby={shown ? `${fieldId}-erro` : undefined}
        data-own-errors=""
        onChange={(e) => commit(e.target.value)}
        onBlur={() => setTouched(true)}
        onInvalid={() => setTouched(true)}
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
      {shown && (
        <small id={`${fieldId}-erro`} className="date-field__error" role="alert">
          {shown}
        </small>
      )}
    </span>
  );
}

/**
 * Dia do mês (recebimento, vencimento, fechamento). Em lançamento só daquele mês o dia
 * precisa existir no mês; no que se repete vale 1 a 31 (nos meses curtos cai no último dia).
 */
export function DayField({
  value,
  onChange,
  month,
  recurring,
  required,
  id,
  label,
}: {
  value: string;
  onChange: (value: string) => void;
  /** AAAA-MM do lançamento (para saber quantos dias o mês tem). */
  month?: string;
  recurring: boolean;
  required?: boolean;
  id?: string;
  label?: string;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [touched, setTouched] = useState(false);
  const autoId = useId();
  const fieldId = id ?? autoId;
  const day = value ? Number(value) : null;
  const [y, m] = (month ?? "").split("-").map(Number);
  const last = month && !recurring ? daysInMonth(y!, m!) : 31;

  let problem: string | null = null;
  if (day !== null && (!Number.isInteger(day) || day < 1)) problem = "Dia inválido: use de 1 a 31.";
  else if (day !== null && day > last)
    problem = month && !recurring ? `${MONTHS[m! - 1]} de ${y} tem ${last} dias. Use um dia entre 1 e ${last}.` : "Dia inválido: use de 1 a 31.";
  else if (required && day === null && touched) problem = "Informe o dia.";
  const hint = !problem && recurring && day !== null && day >= 29 ? "Em meses mais curtos, cai no último dia do mês." : null;

  useLayoutEffect(() => {
    input.current?.setCustomValidity(problem && problem !== "Informe o dia." ? problem : "");
  }, [problem]);

  return (
    <>
      <input
        ref={input}
        id={fieldId}
        type="text"
        inputMode="numeric"
        autoComplete="off"
        maxLength={2}
        placeholder={recurring ? "1 a 31" : `1 a ${last}`}
        value={value}
        required={required}
        aria-label={label}
        aria-invalid={problem ? true : undefined}
        aria-describedby={problem || hint ? `${fieldId}-ajuda` : undefined}
        data-own-errors=""
        onChange={(e) => onChange(e.target.value.replace(/\D/g, "").slice(0, 2))}
        onBlur={() => setTouched(true)}
        onInvalid={() => setTouched(true)}
      />
      {(problem || hint) && (
        <small id={`${fieldId}-ajuda`} className={problem ? "date-field__error" : "muted small"} role={problem ? "alert" : undefined}>
          {problem ?? hint}
        </small>
      )}
    </>
  );
}
