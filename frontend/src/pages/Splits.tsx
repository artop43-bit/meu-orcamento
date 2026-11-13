import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDownLeft,
  ArrowUpRight,
  Check,
  ChevronDown,
  Coins,
  FileText,
  Handshake,
  MessageCircle,
  Plus,
  QrCode,
  Search,
  Trash2,
  TrendingUp,
  TriangleAlert,
  Undo2,
  Users,
} from "lucide-react";

import { errorMessage } from "../api/client";
import { download } from "../api/data";
import {
  SPLITS_KEY,
  sharingApi,
  type Direction,
  type FriendLoan,
  type LoanFrequency,
  type LoanInstallment,
  type LoanMode,
  type LoanTarget,
  type SimulateInput,
  type SplitBoard,
  type SplitPersonRow,
} from "../api/sharing";
import { MoneyInput, requireMoney } from "../components/budget";
import { EmptyGuide } from "../components/help";
import { PixCharge } from "../components/PixCharge";
import { Alert, Button, Kpi, LoadingRegion, PageHeader, Sheet, Skeleton } from "../components/ui";
import { announce } from "../lib/announce";
import { money, parseMoney, shortDate, todayISO } from "../lib/format";

// ---------------------------------------------------------------- textos

const MODES: { value: LoanMode; label: string }[] = [
  { value: "total", label: "Sobre o total" },
  { value: "simple", label: "Simples ao mês" },
  { value: "price", label: "Compostos (parcelas iguais)" },
  { value: "sac", label: "SAC (parcelas que diminuem)" },
  { value: "none", label: "Sem juros" },
];
const MODE_SHORT: Record<LoanMode, string> = {
  none: "sem juros",
  total: "sobre o total",
  simple: "simples ao mês",
  price: "compostos (Price)",
  sac: "SAC",
};
const FREQUENCIES: { value: LoanFrequency; label: string; each: string }[] = [
  { value: "month", label: "Por mês", each: "por mês" },
  { value: "biweek", label: "A cada 15 dias", each: "a cada 15 dias" },
  { value: "week", label: "Por semana", each: "por semana" },
  { value: "day", label: "Por dia", each: "por dia" },
];
const EACH = Object.fromEntries(FREQUENCIES.map((f) => [f.value, f.each])) as Record<LoanFrequency, string>;
const TARGETS: { value: LoanTarget; label: string; field: string }[] = [
  { value: "rate", label: "A taxa", field: "Taxa de juros (%)" },
  { value: "profit", label: "O lucro", field: "Lucro que eu quero" },
  { value: "installment", label: "A parcela", field: "Valor de cada pagamento" },
  { value: "total", label: "O total", field: "Total a receber" },
];
const LATE_FEE = "2";
const LATE_INTEREST = "1";

function num(value: number | string, digits = 2): string {
  return Number(value).toLocaleString("pt-BR", { maximumFractionDigits: digits });
}

function fullDate(iso: string | null): string {
  if (!iso) return "";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
}

function rateLabel(rate: number | string, mode: LoanMode): string {
  if (mode === "none") return "sem juros";
  return `${num(rate)}% ${mode === "total" ? "no total" : "ao mês"}`;
}

function inDays(days: number): string {
  const date = new Date(`${todayISO()}T12:00:00`);
  date.setDate(date.getDate() + days);
  return date.toISOString().slice(0, 10);
}

const FIRST_DUE: Record<LoanFrequency, number> = { day: 1, week: 7, biweek: 15, month: 30 };

function activeLoans(row: SplitPersonRow): FriendLoan[] {
  return row.loans.filter((l) => !l.settled_at);
}

/** A parcela que vale cobrar agora: a primeira em aberto, com multa e juros se atrasada. */
function chargeOf(loan: FriendLoan): number {
  if (!loan.next) return 0;
  return Number(loan.next.open) + Number(loan.next.late_charge);
}

async function refresh(queryClient: ReturnType<typeof useQueryClient>) {
  await queryClient.invalidateQueries({ queryKey: SPLITS_KEY });
  await queryClient.invalidateQueries({ queryKey: ["budget"] });
}

// ---------------------------------------------------------------- anotação simples

function ManualForm({ names, onDone }: { names: string[]; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [person, setPerson] = useState("");
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState("");
  const [direction, setDirection] = useState<Direction>("owes_me");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      await sharingApi.addManual({ person: person.trim(), description: description.trim(), amount: requireMoney(amount), direction });
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
      <Alert tone="error">{error}</Alert>
      <DirectionField name="manual-direction" value={direction} onChange={setDirection} />
      <PeopleList names={names} />
      <div className="grid-2">
        <label>
          Pessoa
          <input value={person} onChange={(e) => setPerson(e.target.value)} list="split-people" required maxLength={60} />
        </label>
        <label>
          Valor
          <MoneyInput value={amount} onChange={setAmount} />
        </label>
      </div>
      <label>
        Descrição
        <input value={description} onChange={(e) => setDescription(e.target.value)} maxLength={120} placeholder="Ex.: Ingresso do show" />
      </label>
      <div className="form-actions">
        <Button type="button" variant="secondary" onClick={onDone}>
          Cancelar
        </Button>
        <Button type="submit" loading={busy}>
          Salvar
        </Button>
      </div>
    </form>
  );
}

function DirectionField({ name, value, onChange }: { name: string; value: Direction; onChange: (value: Direction) => void }) {
  return (
    <fieldset className="radios">
      <legend className="field-label">Quem deve</legend>
      <div className="segmented">
        <label>
          <input type="radio" name={name} checked={value === "owes_me"} onChange={() => onChange("owes_me")} />A pessoa me deve
        </label>
        <label>
          <input type="radio" name={name} checked={value === "i_owe"} onChange={() => onChange("i_owe")} />
          Eu devo à pessoa
        </label>
      </div>
    </fieldset>
  );
}

function PeopleList({ names }: { names: string[] }) {
  return (
    <datalist id="split-people">
      {names.map((n) => (
        <option key={n} value={n} />
      ))}
    </datalist>
  );
}

// ---------------------------------------------------------------- empréstimo com juros

function useDebounced<T>(value: T, delay = 300): T {
  const [current, setCurrent] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setCurrent(value), delay);
    return () => window.clearTimeout(timer);
  }, [value, delay]);
  return current;
}

function LoanForm({ names, onDone }: { names: string[]; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [direction, setDirection] = useState<Direction>("owes_me");
  const [person, setPerson] = useState("");
  const [principal, setPrincipal] = useState("");
  const [target, setTarget] = useState<LoanTarget>("rate");
  const [value, setValue] = useState("");
  const [mode, setMode] = useState<LoanMode>("total");
  const [frequency, setFrequency] = useState<LoanFrequency>("month");
  const [count, setCount] = useState("12");
  const [firstDue, setFirstDue] = useState(inDays(30));
  const [late, setLate] = useState(true);
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const input = useMemo<SimulateInput | null>(() => {
    const amount = parseMoney(principal);
    const times = Number(count);
    if (!amount || Number(amount) <= 0 || !Number.isInteger(times) || times < 1 || !firstDue) return null;
    const base = { principal: amount, mode, target, frequency, count: times, first_due: firstDue, market: true };
    if (mode === "none") return { ...base, target: "rate" };
    if (target === "rate") {
      const rate = Number(value.replace(",", "."));
      return Number.isFinite(rate) && value.trim() !== "" ? { ...base, rate: String(rate) } : null;
    }
    const wanted = parseMoney(value);
    return wanted ? { ...base, value: wanted } : null;
  }, [principal, count, firstDue, mode, target, frequency, value]);
  const debounced = useDebounced(input);
  const simulation = useQuery({
    queryKey: ["friend-loans", "simulate", debounced],
    queryFn: () => sharingApi.simulate(debounced!),
    enabled: debounced !== null,
    retry: false,
    placeholderData: (previous) => previous,
  });
  const result = input ? simulation.data : undefined;
  const receiving = direction === "owes_me";
  const targetInfo = TARGETS.find((t) => t.value === target)!;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (!input) {
      setError("Preencha o valor, o que você quer definir e a quantidade de pagamentos.");
      return;
    }
    setBusy(true);
    try {
      await sharingApi.createLoan({
        ...input,
        market: false,
        person: person.trim(),
        description: description.trim(),
        direction,
        late_fee: late ? LATE_FEE : null,
        late_interest: late ? LATE_INTEREST : null,
      });
      announce(`Empréstimo com ${person.trim()} anotado`);
      await refresh(queryClient);
      onDone();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="inline-form" onSubmit={submit}>
      <Alert tone="error">{error}</Alert>
      <DirectionField name="loan-direction" value={direction} onChange={setDirection} />
      <PeopleList names={names} />
      <div className="grid-2">
        <label>
          Pessoa
          <input value={person} onChange={(e) => setPerson(e.target.value)} list="split-people" required maxLength={60} />
        </label>
        <label>
          {receiving ? "Valor emprestado" : "Valor que peguei"}
          <MoneyInput value={principal} onChange={setPrincipal} />
        </label>
      </div>
      {mode !== "none" && (
        <fieldset className="radios">
          <legend className="field-label">O que você quer definir?</legend>
          <div className="chips" role="group" aria-label="O que você quer definir">
            {TARGETS.map((t) => (
              <button
                key={t.value}
                type="button"
                className="chip-btn"
                aria-pressed={target === t.value}
                onClick={() => {
                  setTarget(t.value);
                  setValue("");
                }}
              >
                {t.label}
              </button>
            ))}
          </div>
        </fieldset>
      )}
      <div className="grid-2">
        {mode !== "none" && (
          <label>
            {target === "total" && !receiving ? "Total a pagar" : targetInfo.field}
            {target === "rate" ? (
              <input
                inputMode="decimal"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                placeholder={mode === "total" ? "Ex.: 5 (% sobre o total)" : "Ex.: 1 (% ao mês)"}
                required
              />
            ) : (
              <MoneyInput value={value} onChange={setValue} />
            )}
          </label>
        )}
        <label>
          Forma dos juros
          <select value={mode} onChange={(e) => setMode(e.target.value as LoanMode)}>
            {MODES.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="grid-2">
        <label>
          Pagamentos
          <select
            value={frequency}
            onChange={(e) => {
              const next = e.target.value as LoanFrequency;
              setFrequency(next);
              setFirstDue(inDays(FIRST_DUE[next]));
            }}
          >
            {FREQUENCIES.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Quantidade
          <input type="number" inputMode="numeric" min={1} max={365} value={count} onChange={(e) => setCount(e.target.value)} required />
        </label>
      </div>
      <div className="grid-2">
        <label>
          Primeiro pagamento
          <input type="date" value={firstDue} onChange={(e) => setFirstDue(e.target.value)} required />
        </label>
        <label className="check loan-form__late">
          <input type="checkbox" checked={late} onChange={(e) => setLate(e.target.checked)} />
          Cobrar atraso ({LATE_FEE}% + {LATE_INTEREST}% ao mês)
        </label>
      </div>
      <label>
        Descrição (opcional)
        <input value={description} onChange={(e) => setDescription(e.target.value)} maxLength={120} placeholder="Ex.: Conserto do carro" />
      </label>
      {simulation.isError && input && <Alert tone="error">{errorMessage(simulation.error)}</Alert>}
      {result && <LoanResult result={result} target={target} receiving={receiving} />}
      <div className="form-actions">
        <Button type="button" variant="secondary" onClick={onDone}>
          Cancelar
        </Button>
        <Button type="submit" loading={busy}>
          Salvar empréstimo
        </Button>
      </div>
    </form>
  );
}

function LoanResult({
  result,
  target,
  receiving,
}: {
  result: NonNullable<Awaited<ReturnType<typeof sharingApi.simulate>>>;
  target: LoanTarget;
  receiving: boolean;
}) {
  const each = result.equal_installments
    ? `${result.count}x ${money(result.installment)}`
    : `de ${money(result.installment)} a ${money(result.last_installment)}`;
  const market = result.market;
  return (
    <section className="loan-result" aria-live="polite" aria-label="Resultado da simulação">
      <div className="stats">
        <div className="stat">
          <span className="stat__label">{target === "rate" || result.mode === "none" ? "Taxa" : "Taxa necessária"}</span>
          <strong className="stat__value tone--ok">{rateLabel(result.rate, result.mode)}</strong>
        </div>
        <div className="stat">
          <span className="stat__label">Cada pagamento ({EACH[result.frequency]})</span>
          <strong className="stat__value">{each}</strong>
        </div>
        <div className="stat">
          <span className="stat__label">{receiving ? "Total a receber" : "Total a pagar"}</span>
          <strong className="stat__value">{money(result.total)}</strong>
        </div>
        <div className="stat">
          <span className="stat__label">{receiving ? "Lucro" : "Juros"}</span>
          <strong className="stat__value">{money(result.profit)}</strong>
        </div>
      </div>
      {result.mode !== "none" && (
        <p className="muted small" style={{ margin: 0 }}>
          Equivale a <strong>{num(result.monthly_equivalent)}% ao mês</strong> ({num(result.yearly_equivalent, 1)}% ao ano).
        </p>
      )}
      {result.usury_warning && (
        <div className="alert alert--info loan-result__note" role="note">
          <TriangleAlert size={16} aria-hidden />
          <span>Acima de 1% ao mês, o limite comum para empréstimo entre pessoas (Lei da Usura). Informação geral, não é orientação jurídica.</span>
        </div>
      )}
      {result.compare.length > 0 && (
        <details className="details">
          <summary>{receiving ? "Mesmo lucro em outras formas" : "Mesmos juros em outras formas"}</summary>
          <ul className="items">
            {result.compare.map((c) => (
              <li key={c.mode} className="item">
                <span className="item__main">
                  <span className="item__title">{MODES.find((m) => m.value === c.mode)?.label ?? c.label}</span>
                  <span className="item__meta">
                    {c.first === c.last ? `${result.count}x ${money(c.first)}` : `de ${money(c.first)} a ${money(c.last)}`}
                  </span>
                </span>
                <strong className="num">{rateLabel(c.rate, c.mode)}</strong>
              </li>
            ))}
          </ul>
        </details>
      )}
      {receiving && result.mode !== "none" && (
        <details className="details">
          <summary>Vale a pena?</summary>
          <ul className="loan-result__facts small">
            {market?.cdb_net && (
              <li>
                No CDB (100% do CDI, {num(market.cdi_year ?? 0)}% ao ano), o mesmo dinheiro renderia cerca de <strong>{money(market.cdb_net)}</strong>{" "}
                líquidos no mesmo prazo.
              </li>
            )}
            {market?.real_profit && (
              <li>
                Descontada a inflação ({num(market.ipca_year ?? 0)}% em 12 meses), o lucro real fica perto de <strong>{money(market.real_profit)}</strong>.
              </li>
            )}
            {result.payback && (
              <li>
                O valor emprestado volta inteiro na <strong>{result.payback}ª</strong> parcela; o resto é lucro.
              </li>
            )}
            {Number(result.loss_if_stops) > 0 && (
              <li>
                Se a pessoa parar de pagar depois da {result.stop_at}ª parcela, você perde <strong>{money(result.loss_if_stops)}</strong> do valor
                emprestado.
              </li>
            )}
          </ul>
        </details>
      )}
      <details className="details">
        <summary>Ver os {result.count} pagamentos</summary>
        <ScheduleTable rows={result.schedule.map((r) => ({ ...r, status: "open" as const }))} />
      </details>
    </section>
  );
}

function ScheduleTable({
  rows,
  actions,
}: {
  rows: { number: number; due_date: string; amount: string; interest: string; principal: string; status: LoanInstallment["status"]; extra?: string }[];
  actions?: (number: number) => React.ReactNode;
}) {
  return (
    <div className="table-scroll">
      <table className="loan-table">
        <thead>
          <tr>
            <th scope="col">Nº</th>
            <th scope="col">Data</th>
            <th scope="col" className="num">
              Valor
            </th>
            <th scope="col" className="num">
              Juros
            </th>
            <th scope="col" className="num">
              Devolução
            </th>
            {actions && <th scope="col">Situação</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.number} className={r.status === "late" ? "is-late" : r.status === "paid" ? "is-paid" : ""}>
              <td>{r.number}</td>
              <td>{fullDate(r.due_date)}</td>
              <td className="num">{money(r.amount)}</td>
              <td className="num">{money(r.interest)}</td>
              <td className="num">{money(r.principal)}</td>
              {actions && (
                <td>
                  <span className="loan-table__status">
                    <span className="small">{r.extra}</span>
                    {actions(r.number)}
                  </span>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------- receber, quitar, cronograma

function ReceiveForm({ loan, onDone }: { loan: FriendLoan; onDone: () => void }) {
  const queryClient = useQueryClient();
  const next = loan.next!;
  const [amount, setAmount] = useState(Number(next.open).toFixed(2).replace(".", ","));
  const [on, setOn] = useState(todayISO());
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const receiving = loan.direction === "owes_me";

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      await sharingApi.receive(loan.id, { number: next.number, amount: requireMoney(amount), on });
      announce(receiving ? "Pagamento recebido" : "Pagamento registrado");
      await refresh(queryClient);
      onDone();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="inline-form" onSubmit={submit}>
      <Alert tone="error">{error}</Alert>
      <p style={{ margin: 0 }}>
        Parcela <strong>{next.number}</strong> de {loan.count}, com vencimento em {fullDate(next.due_date)}:{" "}
        <strong>{money(next.open)}</strong> em aberto.
      </p>
      {Number(next.late_charge) > 0 && (
        <Alert tone="info">
          Atrasada: com multa e juros, fica {money(Number(next.open) + Number(next.late_charge))}. Registre aqui só o valor da parcela; a multa é
          combinada à parte.
        </Alert>
      )}
      <div className="grid-2">
        <label>
          Valor {receiving ? "recebido" : "pago"}
          <MoneyInput value={amount} onChange={setAmount} />
        </label>
        <label>
          Data
          <input type="date" value={on} onChange={(e) => setOn(e.target.value)} required />
        </label>
      </div>
      <p className="muted small" style={{ margin: 0 }}>
        Menos que a parcela deixa o resto em aberto; mais que ela adianta as próximas.
      </p>
      <div className="form-actions">
        <Button type="button" variant="secondary" onClick={onDone}>
          Cancelar
        </Button>
        <Button type="submit" loading={busy}>
          {receiving ? "Recebi" : "Paguei"}
        </Button>
      </div>
    </form>
  );
}

function PayoffForm({ loan, onDone }: { loan: FriendLoan; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [discount, setDiscount] = useState(true);
  const quote = useQuery({ queryKey: ["friend-loans", "payoff", loan.id, discount], queryFn: () => sharingApi.payoffQuote(loan.id, discount) });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function confirm() {
    setError("");
    setBusy(true);
    try {
      await sharingApi.payoff(loan.id, discount);
      announce(`Empréstimo com ${loan.person} quitado`);
      await refresh(queryClient);
      onDone();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      <Alert tone="error">{error}</Alert>
      <label className="check">
        <input type="checkbox" checked={discount} onChange={(e) => setDiscount(e.target.checked)} />
        Tirar os juros das parcelas que ainda não venceram
      </label>
      {quote.data && (
        <div className="stats">
          <div className="stat">
            <span className="stat__label">Falta pagar</span>
            <strong className="stat__value">{money(quote.data.remaining)}</strong>
          </div>
          <div className="stat">
            <span className="stat__label">Desconto</span>
            <strong className="stat__value">{money(quote.data.discount)}</strong>
          </div>
          <div className="stat">
            <span className="stat__label">Para quitar hoje</span>
            <strong className="stat__value tone--ok">{money(quote.data.value)}</strong>
          </div>
        </div>
      )}
      <div className="form-actions">
        <Button type="button" variant="secondary" onClick={onDone}>
          Cancelar
        </Button>
        <Button type="button" loading={busy} onClick={() => void confirm()}>
          Quitar
        </Button>
      </div>
    </div>
  );
}

function reminder(loan: FriendLoan): string {
  const next = loan.next;
  if (!next) return `Oi, ${loan.person}! O empréstimo está quitado. Obrigado!`;
  const late = Number(next.late_charge) > 0;
  const total = Number(next.open) + Number(next.late_charge);
  return (
    `Oi, ${loan.person}! Passando para lembrar da parcela ${next.number}/${loan.count} do empréstimo: ` +
    `${money(late ? total : next.open)}, ${late ? `venceu em ${fullDate(next.due_date)} (com multa e juros)` : `vence em ${fullDate(next.due_date)}`}. ` +
    `Faltam ${money(loan.remaining)} no total.`
  );
}

function LoanSheet({ loan, onClose }: { loan: FriendLoan; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [step, setStep] = useState<"view" | "payoff" | "delete">("view");
  const [error, setError] = useState("");
  const receiving = loan.direction === "owes_me";

  async function act(work: () => Promise<unknown>, message: string) {
    setError("");
    try {
      await work();
      announce(message);
      await refresh(queryClient);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function share() {
    const text = reminder(loan);
    if (navigator.share) {
      await navigator.share({ text }).catch(() => undefined);
    } else {
      await navigator.clipboard.writeText(text).catch(() => undefined);
      announce("Mensagem copiada");
    }
  }

  if (step === "payoff") return <PayoffForm loan={loan} onDone={() => setStep("view")} />;
  if (step === "delete") {
    return (
      <div className="stack">
        <p style={{ margin: 0 }}>
          Apagar o empréstimo com {loan.person}? O que já foi {receiving ? "recebido" : "pago"} continua no Orçamento; os pagamentos previstos saem.
        </p>
        <div className="form-actions">
          <Button type="button" variant="secondary" onClick={() => setStep("view")}>
            Cancelar
          </Button>
          <Button
            type="button"
            onClick={() =>
              void act(async () => {
                await sharingApi.removeLoan(loan.id);
                onClose();
              }, "Empréstimo apagado")
            }
          >
            Apagar
          </Button>
        </div>
      </div>
    );
  }
  return (
    <div className="stack">
      <Alert tone="error">{error}</Alert>
      <div className="stats">
        <div className="stat">
          <span className="stat__label">{receiving ? "Emprestado" : "Peguei"}</span>
          <strong className="stat__value">{money(loan.principal)}</strong>
        </div>
        <div className="stat">
          <span className="stat__label">
            {receiving ? "Recebido" : "Pago"} de {money(loan.total)}
          </span>
          <strong className="stat__value">{money(loan.received)}</strong>
        </div>
        <div className="stat">
          <span className="stat__label">Falta</span>
          <strong className="stat__value">{money(loan.remaining)}</strong>
        </div>
        <div className="stat">
          <span className="stat__label">
            {receiving ? "Lucro recebido" : "Juros pagos"} de {money(loan.profit)}
          </span>
          <strong className="stat__value tone--ok">{money(loan.profit_received)}</strong>
        </div>
      </div>
      <p className="muted small" style={{ margin: 0 }}>
        {rateLabel(loan.rate, loan.mode)} · {MODE_SHORT[loan.mode]} · {loan.count}x {EACH[loan.frequency]}
        {loan.mode !== "none" && ` · equivale a ${num(loan.monthly_equivalent)}% ao mês`}
        {loan.late_fee && ` · atraso: ${num(loan.late_fee)}% + ${num(loan.late_interest ?? 0)}% ao mês`}. Cada pagamento entra no Orçamento do mês como{" "}
        {receiving ? "receita prevista" : "despesa"}.
      </p>
      <ScheduleTable
        rows={loan.installments.map((i) => ({
          ...i,
          extra:
            i.status === "paid"
              ? `${receiving ? "Recebida" : "Paga"} ${shortDate(i.received_at)}`
              : i.status === "partial"
                ? `Parcial · falta ${money(i.open)}`
                : i.status === "late"
                  ? `Atrasada${i.received_amount ? ` · falta ${money(i.open)}` : ""}${Number(i.late_charge) > 0 ? ` · +${money(i.late_charge)}` : ""}`
                  : "Prevista",
        }))}
        actions={(number) => {
          const item = loan.installments.find((i) => i.number === number)!;
          if (item.received_amount && Number(item.open) <= 0)
            return (
              <button
                type="button"
                className="icon-btn"
                aria-label={`Desfazer o pagamento da parcela ${number}`}
                onClick={() => void act(() => sharingApi.undoReceive(loan.id, number), "Pagamento desfeito")}
              >
                <Undo2 size={16} />
              </button>
            );
          if (loan.settled_at) return null;
          return (
            <button
              type="button"
              className="icon-btn"
              aria-label={`Marcar a parcela ${number} como ${receiving ? "recebida" : "paga"}`}
              onClick={() => void act(() => sharingApi.receive(loan.id, { number }), receiving ? "Pagamento recebido" : "Pagamento registrado")}
            >
              <Check size={16} />
            </button>
          );
        }}
      />
      <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
        <Button
          type="button"
          variant="secondary"
          onClick={() =>
            void act(
              () => download(`/friend-loans/${loan.id}/term.pdf`, `termo-emprestimo.pdf`),
              "Download iniciado.",
            )
          }
        >
          <FileText size={16} aria-hidden /> Termo em PDF
        </Button>
        {receiving && !loan.settled_at && (
          <Button type="button" variant="secondary" onClick={() => void share()}>
            <MessageCircle size={16} aria-hidden /> Mensagem para {loan.person.split(" ")[0]}
          </Button>
        )}
        {!loan.settled_at && (
          <Button type="button" variant="secondary" onClick={() => setStep("payoff")}>
            <Handshake size={16} aria-hidden /> Quitar antecipado
          </Button>
        )}
        <Button type="button" variant="secondary" onClick={() => setStep("delete")}>
          <Trash2 size={16} aria-hidden /> Apagar
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- linha de cada pessoa

function LoanSummary({ loan, onOpen }: { loan: FriendLoan; onOpen: () => void }) {
  const receiving = loan.direction === "owes_me";
  const late = loan.installments.filter((i) => i.status === "late");
  const pct = Number(loan.total) ? (Number(loan.received) / Number(loan.total)) * 100 : 0;
  return (
    <div className="loan">
      <div className="loan__head">
        <span className="badge">{loan.settled_at ? "Quitado" : receiving ? "Empréstimo com juros" : "Eu devo · com juros"}</span>
        <span className="muted small">
          {money(loan.principal)} · {rateLabel(loan.rate, loan.mode)} · {loan.count}x {EACH[loan.frequency]}
        </span>
      </div>
      <div className="bar" aria-hidden>
        <div className="bar__fill" style={{ width: `${Math.min(pct, 100)}%` }} />
      </div>
      <div className="split small">
        <span>
          <strong>
            {loan.paid_count} de {loan.count}
          </strong>{" "}
          {receiving ? "recebidas" : "pagas"} · {money(loan.received)} de {money(loan.total)}
        </span>
        <span>
          falta <strong className="num">{money(loan.remaining)}</strong>
        </span>
      </div>
      <div className="split small">
        {late.length > 0 ? (
          <span className="tone--error">
            <strong>{late.length === 1 ? "1 atrasada" : `${late.length} atrasadas`}</strong> · desde {shortDate(late[0]!.due_date)}
            {Number(loan.late_amount) > 0 && ` · com multa e juros ${money(loan.late_amount)}`}
          </span>
        ) : loan.next ? (
          <span className="muted">
            Próxima:{" "}
            <strong>
              {fullDate(loan.next.due_date)} · {money(loan.next.open)}
            </strong>
          </span>
        ) : (
          <span className="muted">Tudo {receiving ? "recebido" : "pago"}</span>
        )}
        <span className="tone--ok">
          {receiving ? "lucro" : "juros"} {money(loan.profit_received)} de {money(loan.profit)}
        </span>
      </div>
      <button type="button" className="link-btn small" onClick={onOpen}>
        Ver cronograma, termo e quitação
      </button>
    </div>
  );
}

function PersonRow({
  entry,
  open,
  onToggle,
  onSettle,
  onCharge,
  onReceive,
  onLoan,
}: {
  entry: SplitPersonRow;
  open: boolean;
  onToggle: () => void;
  onSettle: () => void;
  onCharge: (amount: number) => void;
  onReceive: (loan: FriendLoan) => void;
  onLoan: (loan: FriendLoan) => void;
}) {
  const queryClient = useQueryClient();
  const balance = Number(entry.balance);
  const loans = activeLoans(entry);
  const lateCount = loans.reduce((sum, l) => sum + l.late_count, 0);
  const main = loans.find((l) => l.next) ?? null;
  const parts = [
    loans.length ? `${loans.length} ${loans.length === 1 ? "empréstimo" : "empréstimos"}` : "",
    entry.items.length ? `${entry.items.length} ${entry.items.length === 1 ? "anotação" : "anotações"}` : "",
    lateCount ? (lateCount === 1 ? "parcela atrasada" : `${lateCount} parcelas atrasadas`) : "",
  ].filter(Boolean);
  const paid = loans.reduce((sum, l) => sum + l.paid_count, 0);
  const total = loans.reduce((sum, l) => sum + l.count, 0);
  const id = `person-${entry.person.replace(/\W+/g, "-")}`;

  async function remove(shareId: string) {
    await sharingApi.remove(shareId);
    await queryClient.invalidateQueries({ queryKey: SPLITS_KEY });
  }

  const charge = main && main.direction === "owes_me" ? chargeOf(main) : balance;
  return (
    <section className={`card person-row${open ? " is-open" : ""}`}>
      <button type="button" className="person-row__head" aria-expanded={open} aria-controls={id} onClick={onToggle}>
        <span className="person-row__avatar" aria-hidden>
          {entry.person.trim().charAt(0).toUpperCase()}
        </span>
        <span className="person-row__who">
          <strong>{entry.person}</strong>
          <span className="muted small">{parts.join(" · ") || "acertado"}</span>
        </span>
        <span className="person-row__progress">
          {total > 0 ? (
            <span className="person-row__bar">
              <span className="bar" aria-hidden>
                <span className="bar__fill" style={{ width: `${(paid / total) * 100}%` }} />
              </span>
              <span className="small muted">
                {paid} de {total} parcelas{lateCount ? ` · ${lateCount} atrasada${lateCount > 1 ? "s" : ""}` : ""}
              </span>
            </span>
          ) : (
            <span className="small muted">sem empréstimo</span>
          )}
        </span>
        <span className={`person-row__balance ${lateCount ? "tone--error" : balance >= 0 ? "tone--ok" : "tone--error"}`}>
          {balance > 0 ? `te deve ${money(balance)}` : balance < 0 ? `você deve ${money(-balance)}` : "zerado"}
        </span>
        <span className="person-row__chev" aria-hidden>
          <ChevronDown size={18} />
        </span>
      </button>
      {open && (
        <div className="person-row__body" id={id}>
          <div className={`person-row__grid${entry.loans.length && entry.items.length ? "" : " person-row__grid--single"}`}>
            {entry.loans.length > 0 && (
              <div className="stack">
                {entry.loans.map((loan) => (
                  <LoanSummary key={loan.id} loan={loan} onOpen={() => onLoan(loan)} />
                ))}
              </div>
            )}
            {entry.items.length > 0 && (
              <ul className="items">
                {entry.items.map((s) => (
                  <li key={s.id} className="item">
                    <span className="item__main">
                      <span className="item__title">{s.description}</span>
                      <span className="item__meta">
                        {s.direction === "owes_me" ? "Deve a você" : "Você deve"} · {shortDate(s.created_at.slice(0, 10))}
                      </span>
                    </span>
                    <strong className="num">{money(s.amount)}</strong>
                    <button type="button" className="icon-btn" aria-label={`Remover ${s.description}`} onClick={() => void remove(s.id)}>
                      <Trash2 size={16} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="person-row__actions">
            {main && (
              <Button type="button" onClick={() => onReceive(main)}>
                <Check size={16} aria-hidden /> {main.direction === "owes_me" ? "Recebi a parcela" : "Paguei a parcela"}
              </Button>
            )}
            {balance > 0 && charge > 0 && (
              <Button type="button" variant={main ? "secondary" : "primary"} onClick={() => onCharge(charge)}>
                <QrCode size={16} aria-hidden /> Cobrar via Pix
              </Button>
            )}
            {entry.items.length > 0 && (
              <Button type="button" variant="secondary" onClick={onSettle}>
                <Handshake size={16} aria-hidden /> Acertar contas
              </Button>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

function SettleForm({ person, balance, onDone }: { person: string; balance: number; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [record, setRecord] = useState(balance > 0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function confirm() {
    setError("");
    setBusy(true);
    try {
      await sharingApi.settle(person, record && balance > 0);
      announce(`Contas acertadas com ${person}`);
      await refresh(queryClient);
      onDone();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      <Alert tone="error">{error}</Alert>
      <p style={{ margin: 0 }}>
        {balance > 0 ? (
          <>
            {person} pagou a você <strong>{money(balance)}</strong>?
          </>
        ) : balance < 0 ? (
          <>
            Você pagou <strong>{money(-balance)}</strong> a {person}?
          </>
        ) : (
          <>As contas com {person} estão zeradas.</>
        )}{" "}
        As anotações em aberto com {person} ficam quitadas (os empréstimos com juros seguem no cronograma deles).
      </p>
      {balance > 0 && (
        <label className="check">
          <input type="checkbox" checked={record} onChange={(e) => setRecord(e.target.checked)} />
          Lançar o reembolso como receita deste mês
        </label>
      )}
      <div className="form-actions">
        <Button type="button" variant="secondary" onClick={onDone}>
          Cancelar
        </Button>
        <Button type="button" loading={busy} onClick={() => void confirm()}>
          Acertar contas
        </Button>
      </div>
    </div>
  );
}

function NewEntry({ names, onDone }: { names: string[]; onDone: () => void }) {
  const [kind, setKind] = useState<"simple" | "loan">("simple");
  return (
    <div className="stack">
      <fieldset className="radios">
        <legend className="field-label">Tipo</legend>
        <div className="segmented">
          <label>
            <input type="radio" name="entry-kind" checked={kind === "simple"} onChange={() => setKind("simple")} />
            Anotação simples
          </label>
          <label>
            <input type="radio" name="entry-kind" checked={kind === "loan"} onChange={() => setKind("loan")} />
            Empréstimo com juros e parcelas
          </label>
        </div>
      </fieldset>
      {kind === "simple" ? <ManualForm names={names} onDone={onDone} /> : <LoanForm names={names} onDone={onDone} />}
    </div>
  );
}

// ---------------------------------------------------------------- tela

type Filter = "all" | "loans" | "late" | "owes" | "iowe";
const FILTERS: { value: Filter; label: string; test: (row: SplitPersonRow) => boolean }[] = [
  { value: "all", label: "Todos", test: () => true },
  { value: "loans", label: "Com empréstimo", test: (r) => activeLoans(r).length > 0 },
  { value: "late", label: "Atrasados", test: (r) => activeLoans(r).some((l) => l.late_count > 0) },
  { value: "owes", label: "Te devem", test: (r) => Number(r.balance) > 0 },
  { value: "iowe", label: "Você deve", test: (r) => Number(r.balance) < 0 },
];

function plain(text: string): string {
  return text
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();
}

/** Divisões: quem deve a quem, anotações, empréstimos com juros e acerto de contas. */
export default function SplitsPage() {
  const board = useQuery({ queryKey: SPLITS_KEY, queryFn: sharingApi.board });
  const [adding, setAdding] = useState(false);
  const [settling, setSettling] = useState<{ person: string; balance: number } | null>(null);
  const [charging, setCharging] = useState<{ person: string; balance: number } | null>(null);
  const [receivingId, setReceivingId] = useState<string | null>(null);
  const [loanId, setLoanId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [opened, setOpened] = useState<Set<string> | null>(null);
  const data: SplitBoard | undefined = board.data;
  const people = data?.people ?? [];
  const allLoans = people.flatMap((p) => p.loans);
  const receivingLoan = allLoans.find((l) => l.id === receivingId) ?? null;
  const sheetLoan = allLoans.find((l) => l.id === loanId) ?? null;
  // Começa com a primeira pessoa aberta; depois vale o que a pessoa abrir ou fechar.
  const open = opened ?? new Set(people.slice(0, 1).map((p) => p.person));
  const needle = plain(query.trim());
  const rule = FILTERS.find((f) => f.value === filter)!;
  const shown = people.filter((p) => rule.test(p) && (!needle || plain(p.person).includes(needle)));
  const allOpen = shown.length > 0 && shown.every((p) => open.has(p.person));
  const totals = data?.loans;

  function toggle(person: string) {
    const next = new Set(open);
    if (next.has(person)) next.delete(person);
    else next.add(person);
    setOpened(next);
  }

  return (
    <>
      <PageHeader
        title="Divisões"
        subtitle="Quem deve a quem: despesas divididas, anotações e empréstimos com juros."
        actions={
          <Button type="button" onClick={() => setAdding(true)}>
            <Plus size={16} /> Nova anotação
          </Button>
        }
      />
      {board.isPending && (
        <LoadingRegion label="Carregando as divisões">
          <Skeleton height={180} />
        </LoadingRegion>
      )}
      {board.isError && <Alert tone="error">{errorMessage(board.error)}</Alert>}
      {data && totals && (
        <div className="kpis" style={{ marginBottom: 20 }}>
          <Kpi icon={<ArrowDownLeft size={18} />} label="Te devem" value={money(data.owed_to_me)} foot="Soma do que está em aberto" />
          <Kpi icon={<ArrowUpRight size={18} />} tone="expense" label="Você deve" value={money(data.i_owe)} foot="Soma do que está em aberto" />
          <Kpi
            icon={<Coins size={18} />}
            label="Emprestado com juros"
            value={money(totals.lent)}
            foot={totals.lent_count ? `falta receber ${money(totals.to_receive)}` : "Nenhum empréstimo em andamento"}
          />
          <Kpi
            icon={<TrendingUp size={18} />}
            label="Lucro com juros"
            value={money(totals.profit_received)}
            foot={
              totals.lent_count
                ? `de ${money(totals.profit_expected)} previstos${totals.yearly ? ` · ${num(totals.yearly, 1)}% ao ano` : ""}`
                : "Recebido em juros"
            }
          />
        </div>
      )}
      {data && people.length === 0 && (
        <section className="card">
          <EmptyGuide
            icon={<Users size={22} />}
            title="Nada em aberto"
            text="Divida uma despesa ao editá-la no Orçamento (botão “Dividir”) ou anote aqui o que alguém te deve, o que você deve ou um empréstimo com juros e parcelas."
          />
        </section>
      )}
      {data && people.length > 0 && (
        <>
          <div className="list-tools list-tools--pills person-tools" role="search" aria-label="Filtrar pessoas">
            <label className="list-tools__search">
              <Search size={16} aria-hidden />
              <span className="sr-only">Buscar pessoa</span>
              <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Buscar pessoa" />
            </label>
            <span className="pill-group" role="group" aria-label="Filtrar">
              {FILTERS.map((f) => (
                <button key={f.value} type="button" className="chip-btn" aria-pressed={filter === f.value} onClick={() => setFilter(f.value)}>
                  {f.label} ({people.filter(f.test).length})
                </button>
              ))}
            </span>
            <button
              type="button"
              className="chip-btn person-tools__all"
              aria-pressed={allOpen}
              onClick={() => setOpened(allOpen ? new Set() : new Set(shown.map((p) => p.person)))}
            >
              {allOpen ? "Fechar todos" : "Abrir todos"}
            </button>
          </div>
          {shown.length === 0 ? (
            <p className="muted">Ninguém encontrado com esse filtro.</p>
          ) : (
            <div className="person-rows">
              {shown.map((entry) => (
                <PersonRow
                  key={entry.person}
                  entry={entry}
                  open={open.has(entry.person)}
                  onToggle={() => toggle(entry.person)}
                  onSettle={() => setSettling({ person: entry.person, balance: Number(entry.balance) })}
                  onCharge={(amount) => setCharging({ person: entry.person, balance: amount })}
                  onReceive={(loan) => setReceivingId(loan.id)}
                  onLoan={(loan) => setLoanId(loan.id)}
                />
              ))}
            </div>
          )}
        </>
      )}
      {data && data.history.length > 0 && (
        <details className="details" style={{ marginTop: 20 }}>
          <summary>Acertos recentes</summary>
          <ul className="items">
            {data.history.map((s) => (
              <li key={s.id} className="item">
                <span className="item__main">
                  <span className="item__title">
                    {s.person} · {s.description}
                  </span>
                  <span className="item__meta">Acertado em {shortDate(s.settled_at?.slice(0, 10) ?? null)}</span>
                </span>
                <span className="num muted">{money(s.amount)}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
      <Sheet open={adding} title="Nova anotação" onClose={() => setAdding(false)}>
        {adding && <NewEntry names={data?.names ?? []} onDone={() => setAdding(false)} />}
      </Sheet>
      <Sheet open={charging !== null} title={`Cobrar ${charging?.person ?? ""} via Pix`} onClose={() => setCharging(null)}>
        {charging && <PixCharge person={charging.person} amount={charging.balance} />}
      </Sheet>
      <Sheet open={settling !== null} title={`Acertar contas${settling ? ` com ${settling.person}` : ""}`} onClose={() => setSettling(null)}>
        {settling && <SettleForm person={settling.person} balance={settling.balance} onDone={() => setSettling(null)} />}
      </Sheet>
      <Sheet
        open={receivingLoan !== null}
        title={receivingLoan?.direction === "i_owe" ? `Paguei a ${receivingLoan.person}` : `Recebi de ${receivingLoan?.person ?? ""}`}
        onClose={() => setReceivingId(null)}
      >
        {receivingLoan?.next && <ReceiveForm loan={receivingLoan} onDone={() => setReceivingId(null)} />}
      </Sheet>
      <Sheet open={sheetLoan !== null} wide title={`Empréstimo · ${sheetLoan?.person ?? ""}`} onClose={() => setLoanId(null)}>
        {sheetLoan && <LoanSheet key={sheetLoan.id} loan={sheetLoan} onClose={() => setLoanId(null)} />}
      </Sheet>
    </>
  );
}
