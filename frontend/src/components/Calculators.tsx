import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { BarChart3, CreditCard, FastForward, Gift, ShieldCheck, Target, TrendingUp, type LucideIcon } from "lucide-react";

import { analysisApi, type Inflation } from "../api/analysis";
import { budgetApi } from "../api/budget";
import { errorMessage } from "../api/client";
import { hasCredit, useCards } from "../api/extras";
import { useAccounts } from "../api/money";
import { DateField } from "./DateField";

import { cashOrInstallments, compound, emergencyFund, prepay, savingPlan, type RatePeriod } from "../lib/calculators";
import { addMonths, money, monthLabel, parseMoney, thisMonth, todayISO } from "../lib/format";
import { cardCheck, cashCheck, installmentImpact, parseNumber, safestCount, type ForecastMonth } from "../lib/installmentImpact";
import { announce } from "../lib/announce";
import { MoneyInput } from "./budget";
import { Tip } from "./help";
import { Button } from "./ui";
import { compactValue } from "./chart/format";
import { CountUp } from "./CountUp";

type Kind = "compound" | "plan" | "cash" | "prepay" | "reserve" | "inflation" | "bonus";

const KINDS: { key: Kind; label: string; short: string; text: string; icon: LucideIcon }[] = [
  { key: "compound", label: "Juros compostos", short: "Quanto um valor rende", text: "Quanto um valor rende com aportes mensais.", icon: TrendingUp },
  { key: "plan", label: "Guardar por mês", short: "Chegar a uma meta", text: "O aporte mensal para chegar a um valor numa data.", icon: Target },
  {
    key: "cash",
    label: "Parcelar ou à vista",
    short: "E no meu orçamento?",
    text: "Se o desconto à vista compensa e quanto a parcela pesa nos seus próximos meses.",
    icon: CreditCard,
  },
  { key: "prepay", label: "Antecipar parcelas", short: "Quitar ou aplicar", text: "Antecipar parcelas de uma dívida ou deixar o dinheiro aplicado.", icon: FastForward },
  { key: "reserve", label: "Reserva", short: "Valor ideal", text: "O valor ideal da reserva a partir dos gastos essenciais.", icon: ShieldCheck },
  { key: "inflation", label: "Inflação", short: "Corrigir pelo IPCA", text: "Quanto um valor de uma data antiga vale hoje, pelo IPCA do Banco Central.", icon: BarChart3 },
  { key: "bonus", label: "13º e restituição", short: "Dinheiro extra", text: "Estimativa do 13º salário e como dividir o dinheiro extra antes de ele chegar.", icon: Gift },
];

const m = (v: string) => Number(parseMoney(v) ?? 0);
const pctText = (v: number) => `${v.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
const onlyNumber = (v: string) => v.replace(/[^\d,.]/g, "");

/** Taxa do CDI (ao ano), para preencher o rendimento; null enquanto não carrega. */
function useCdi(): number | null {
  const indicators = useQuery({ queryKey: ["indicators"], queryFn: analysisApi.indicators, staleTime: 3_600_000 });
  return indicators.data?.available && indicators.data.cdi ? indicators.data.cdi.value : null;
}

/** Rendimento com "% ao mês/ao ano"; começa no CDI atual e pode ser editado. */
function RateField({
  label,
  value,
  onChange,
  period,
  setPeriod,
  tip,
  cdi,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  period: RatePeriod;
  setPeriod: (p: RatePeriod) => void;
  tip?: string;
  cdi?: number | null;
}) {
  return (
    <>
      <label>
        <span className="field-label">
          {label} {tip && <Tip>{tip}</Tip>}
        </span>
        <span className="affix">
          <span className="affix__box">
            <input inputMode="decimal" value={value} onChange={(e) => onChange(onlyNumber(e.target.value))} />
            <span className="affix__unit">%</span>
          </span>
          {cdi != null && (
            <button
              type="button"
              className="affix__chip"
              title="Usar o CDI atual"
              onClick={() => {
                onChange(cdi.toLocaleString("pt-BR"));
                setPeriod("yearly");
              }}
            >
              CDI {cdi.toLocaleString("pt-BR")}%
            </button>
          )}
        </span>
      </label>
      <label>
        Período da taxa
        <select value={period} onChange={(e) => setPeriod(e.target.value as RatePeriod)}>
          <option value="monthly">Ao mês</option>
          <option value="yearly">Ao ano</option>
        </select>
      </label>
    </>
  );
}

/** Rendimento inicial: o CDI quando chega, sem atropelar o que a pessoa já digitou. */
function useRate(cdi: number | null, fallback: string): [string, (v: string) => void] {
  const [rate, setRate] = useState(fallback);
  const [edited, setEdited] = useState(false);
  useEffect(() => {
    if (!edited && cdi != null) setRate(cdi.toLocaleString("pt-BR"));
  }, [cdi, edited]);
  return [
    rate,
    (v) => {
      setEdited(true);
      setRate(v);
    },
  ];
}

function Field({ label, unit, children, tip }: { label: string; unit?: string; children: ReactNode; tip?: string }) {
  return (
    <label>
      <span className="field-label">
        {label} {tip && <Tip>{tip}</Tip>}
      </span>
      {unit ? (
        <span className="affix__box">
          {children}
          <span className="affix__unit">{unit}</span>
        </span>
      ) : (
        children
      )}
    </label>
  );
}

function NumberInput({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return <input inputMode="decimal" value={value} onChange={(e) => onChange(onlyNumber(e.target.value))} />;
}

/** Botões rápidos (3×, 6×...) com um campo para outro valor. */
function Quick({ label, options, value, onChange, suffix }: { label: string; options: number[]; value: string; onChange: (v: string) => void; suffix: string }) {
  return (
    <fieldset className="radios calc-quick">
      <legend className="field-label">{label}</legend>
      <div className="calc-quick__row">
        {options.map((o) => (
          <button key={o} type="button" className="calc-quick__btn" aria-pressed={parseNumber(value) === o} onClick={() => onChange(String(o))}>
            {o}
            {suffix}
          </button>
        ))}
        <span className="affix__box calc-quick__other">
          <input inputMode="numeric" aria-label={`${label}: outro valor`} value={value} onChange={(e) => onChange(e.target.value.replace(/\D/g, ""))} />
          <span className="affix__unit">{suffix}</span>
        </span>
      </div>
    </fieldset>
  );
}

/** Resultado em destaque: rótulo, número principal grande, detalhes e um mini gráfico. */
function Hero({ tag, label, figure, children, chart, tone = "accent" }: { tag?: string; label: string; figure: string; children?: ReactNode; chart?: ReactNode; tone?: "accent" | "neutral" }) {
  return (
    <div className={`calc-hero calc-hero--${tone}`} aria-live="polite">
      {tag && <span className="calc-hero__tag">{tag}</span>}
      <span className="calc-hero__label">{label}</span>
      <span className="calc-figure">
        <CountUp text={figure} duration={450} />
      </span>
      {children}
      {chart && <div className="calc-hero__chart">{chart}</div>}
    </div>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="calc-stat">
      <span className="calc-stat__label">{label}</span>
      <span className="calc-stat__value num">{value}</span>
      {hint && <span className="calc-stat__hint">{hint}</span>}
    </div>
  );
}

/** Barras horizontais comparando valores (o maior ocupa a largura toda). */
function Compare({ rows }: { rows: { label: string; value: number; tone?: "accent" | "muted" | "warn" }[] }) {
  const max = Math.max(...rows.map((r) => Math.abs(r.value)), 1);
  return (
    <div className="calc-compare" role="img" aria-label={rows.map((r) => `${r.label}: ${money(r.value)}`).join("; ")}>
      {rows.map((r) => (
        <div key={r.label} className="calc-compare__row">
          <span>{r.label}</span>
          <span className="calc-compare__track">
            <span className={`calc-compare__fill calc-compare__fill--${r.tone ?? "accent"}`} style={{ width: `${(Math.abs(r.value) / max) * 100}%` }} />
          </span>
        </div>
      ))}
    </div>
  );
}

/** Curva de crescimento (juros compostos). */
function Growth({ points, invested }: { points: number[]; invested: number[] }) {
  if (points.length < 2) return null;
  const max = Math.max(...points, 1);
  const w = 300;
  const h = 80;
  const path = (values: number[]) => values.map((v, i) => `${i === 0 ? "M" : "L"}${((i / (values.length - 1)) * w).toFixed(1)},${(h - (v / max) * h).toFixed(1)}`).join(" ");
  return (
    <svg className="calc-growth" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" role="img" aria-label="Evolução do saldo e do valor aportado">
      <path d={`${path(points)} L${w},${h} L0,${h} Z`} className="calc-growth__area" />
      <path d={path(points)} className="calc-growth__line" />
      <path d={path(invested)} className="calc-growth__base" />
    </svg>
  );
}

function CompoundCalc({ cdi }: { cdi: number | null }) {
  const [initial, setInitial] = useState("1.000,00");
  const [monthly, setMonthly] = useState("300,00");
  const [rate, setRate] = useRate(cdi, "10,5");
  const [period, setPeriod] = useState<RatePeriod>("yearly");
  const [years, setYears] = useState("5");
  const months = Math.min(720, Math.round(parseNumber(years) * 12));
  const r = compound(m(initial), m(monthly), parseNumber(rate), period, months);
  const invested = r.points.map((_, i) => m(initial) + m(monthly) * (i + 1));
  return (
    <div className="calc-layout">
      <div className="calc-inputs grid-2">
        <label>
          Valor inicial
          <MoneyInput value={initial} onChange={setInitial} required={false} />
        </label>
        <label>
          Aporte por mês
          <MoneyInput value={monthly} onChange={setMonthly} required={false} />
        </label>
        <RateField label="Rendimento" value={rate} onChange={setRate} period={period} setPeriod={setPeriod} cdi={cdi} tip="Rentabilidade esperada, antes ou depois do imposto: use a mesma base para comparar." />
        <Field label="Prazo" unit="anos">
          <NumberInput value={years} onChange={setYears} />
        </Field>
      </div>
      <Hero label={`Em ${years || 0} ano(s) você terá`} figure={money(r.final)} chart={<Growth points={r.points} invested={invested} />}>
        <div className="calc-stats">
          <Stat label="Você aporta" value={money(r.invested)} />
          <Stat label="Os juros somam" value={money(r.interest)} />
        </div>
      </Hero>
    </div>
  );
}

function PlanCalc({ cdi }: { cdi: number | null }) {
  const [target, setTarget] = useState("20.000,00");
  const [current, setCurrent] = useState("0,00");
  const [rate, setRate] = useRate(cdi, "10,5");
  const [period, setPeriod] = useState<RatePeriod>("yearly");
  const [months, setMonths] = useState("24");
  const n = Math.round(parseNumber(months));
  const r = savingPlan(m(target), m(current), parseNumber(rate), period, n);
  const saved = r.monthly * n;
  return (
    <div className="calc-layout">
      <div className="calc-inputs grid-2">
        <label>
          Valor desejado
          <MoneyInput value={target} onChange={setTarget} required={false} />
        </label>
        <label>
          Já guardado
          <MoneyInput value={current} onChange={setCurrent} required={false} />
        </label>
        <RateField label="Rendimento" value={rate} onChange={setRate} period={period} setPeriod={setPeriod} cdi={cdi} />
        <Field label="Prazo" unit="meses">
          <NumberInput value={months} onChange={setMonths} />
        </Field>
      </div>
      <Hero
        label="Guarde por mês"
        figure={money(r.monthly)}
        chart={
          <Compare
            rows={[
              { label: "Já guardado", value: m(current), tone: "muted" },
              { label: "Seus aportes", value: saved },
              { label: "Rendimentos", value: Math.max(0, r.interest), tone: "muted" },
            ]}
          />
        }
      >
        <div className="calc-stats">
          <Stat label="Aportes no período" value={money(saved)} />
          <Stat label="Rendimentos cobrem" value={money(Math.max(0, r.interest))} />
        </div>
      </Hero>
    </div>
  );
}

const COUNT_OPTIONS = [3, 6, 10, 12];

/** Cartões de crédito com limite (para conferir se a compra cabe). */
function useCreditCards() {
  const cards = useCards();
  return (cards.data ?? []).filter((s) => hasCredit(s.card) && Number(s.card.limit_amount ?? 0) > 0);
}

function CashCalc({ cdi }: { cdi: number | null }) {
  const [price, setPrice] = useState("3.000,00");
  const [discount, setDiscount] = useState("5");
  const [count, setCount] = useState("10");
  const [rate, setRate] = useRate(cdi, "10,5");
  const [period, setPeriod] = useState<RatePeriod>("yearly");
  const [first, setFirst] = useState(addMonths(thisMonth(), 1));
  const [cardId, setCardId] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState("");
  const [saveError, setSaveError] = useState("");

  const n = Math.min(48, Math.max(1, Math.round(parseNumber(count)) || 1));
  const total = m(price);
  const r = cashOrInstallments(total, parseNumber(discount), n, parseNumber(rate), period);

  // Previsão real a partir do mês da 1ª parcela (24 meses: cobre as sugestões de até 24×).
  const span = Math.max(24, n);
  const projection = useQuery({
    queryKey: ["analysis", "calc-projection", first, span],
    queryFn: () => analysisApi.projection(first, Math.min(36, span)),
    enabled: Boolean(first),
    staleTime: 60_000,
  });
  const overview = useQuery({ queryKey: ["analysis", "overview", thisMonth()], queryFn: () => analysisApi.overview(thisMonth()), staleTime: 60_000 });
  const accounts = useAccounts();
  const cards = useCreditCards();

  const forecast: ForecastMonth[] = useMemo(
    () =>
      (projection.data ?? []).map((p) => ({ month: p.month, income: Number(p.income), expenses: Number(p.expenses), installments: Number(p.installments ?? 0) })),
    [projection.data],
  );
  const impact = forecast.length ? installmentImpact(forecast, r.parcel, n, first) : null;
  const suggestion = forecast.length ? safestCount(forecast, total, first) : null;

  const balance = (accounts.data ?? [])
    .filter((a) => !a.account.archived && a.account.kind !== "benefit" && a.account.kind !== "transport")
    .reduce((sum, a) => sum + Math.min(Number(a.balance), Number(a.end_of_month)), 0);
  const reserve = Number(overview.data?.score.reserve_total ?? 0);
  const cash = accounts.data ? cashCheck(balance, r.cash, reserve) : null;

  const card = cards.find((c) => c.card.id === cardId);
  const limit = card ? cardCheck(Number(card.card.limit_amount), Number(card.available ?? 0), total) : null;

  async function launch() {
    setSaving(true);
    setSaveError("");
    try {
      const day = String(Math.min(28, Number(todayISO().slice(8)))).padStart(2, "0");
      const name = description.trim() || "Compra parcelada";
      for (let i = 0; i < n; i++) {
        await budgetApi.createPlanned({
          date: `${addMonths(first, i)}-${day}`,
          description: `${name} (${i + 1}/${n})`,
          amount: r.parcel.toFixed(2),
          category_id: null,
          notes: `Simulado na calculadora: ${n}× de ${money(r.parcel)}${card ? ` no ${card.card.name}` : ""}.`,
        });
      }
      const message = `${n} parcelas de ${money(r.parcel)} lançadas no Planejamento a partir de ${monthLabel(first).toLowerCase()}.`;
      setSaved(message);
      announce(message);
    } catch (err) {
      setSaveError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  const maxAbs = impact ? Math.max(1, ...impact.months.flatMap((x) => [Math.abs(x.before), Math.abs(x.after)])) : 1;

  return (
    <div className="stack">
      <div className="calc-layout">
        <div className="calc-inputs stack">
          <label>
            Preço
            <MoneyInput value={price} onChange={setPrice} required={false} />
          </label>
          <div className="grid-2">
            <Field label="Desconto à vista" unit="%">
              <NumberInput value={discount} onChange={setDiscount} />
            </Field>
            <label>
              <span className="field-label">
                1ª parcela em <Tip>No cartão, a 1ª parcela costuma vir na fatura do mês seguinte.</Tip>
              </span>
              <DateField month value={first} min={thisMonth()} onChange={(v) => v && setFirst(v)} />
            </label>
          </div>
          <Quick label="Parcelas sem juros" options={COUNT_OPTIONS} value={count} onChange={setCount} suffix="×" />
          <div className="grid-2">
            <RateField label="Rendimento do dinheiro aplicado" value={rate} onChange={setRate} period={period} setPeriod={setPeriod} cdi={cdi} />
          </div>
          {cards.length > 0 && (
            <label>
              Cartão
              <select value={cardId} onChange={(e) => setCardId(e.target.value)}>
                <option value="">Sem cartão (não conferir limite)</option>
                {cards.map((c) => (
                  <option key={c.card.id} value={c.card.id}>
                    {c.card.name}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
        <Hero
          tag={r.better === "cash" ? "À vista sai mais barato" : "Parcelar sai mais barato"}
          label="Você economiza"
          figure={money(r.difference)}
          chart={
            <Compare
              rows={[
                { label: "À vista", value: r.cash, tone: r.better === "cash" ? "accent" : "muted" },
                { label: "Parcelado", value: r.installmentsPresent, tone: r.better === "cash" ? "muted" : "accent" },
              ]}
            />
          }
        >
          <div className="calc-stats">
            <Stat label="À vista" value={money(r.cash)} />
            <Stat label={`${n}× de ${money(r.parcel)} valem hoje`} value={money(r.installmentsPresent)} />
          </div>
          <p className="calc-note">
            O desconto mínimo para empatar é <strong>{pctText(r.breakEvenDiscount)}</strong>. Acima disso, pagar à vista compensa.
          </p>
          {cash && (
            <p className={`calc-check ${cash.covers ? "calc-check--ok" : "calc-check--warn"}`}>
              {cash.covers
                ? `Seu saldo nas contas (${money(cash.balance)}) cobre o à vista e ainda sobram ${money(cash.leftover)}, sem tocar na reserva de emergência.`
                : cash.coversWithReserve
                  ? `Seu saldo nas contas (${money(cash.balance)}) não cobre o à vista: faltam ${money(cash.missing)}, que sairiam da reserva de emergência (${money(cash.reserve)}).`
                  : `Seu saldo nas contas (${money(cash.balance)}) não cobre o à vista: faltam ${money(cash.missing)}.`}
            </p>
          )}
        </Hero>
      </div>

      <section className="calc-impact" aria-labelledby="impact-title">
        <div className="calc-impact__head">
          <h3 id="impact-title">E no meu orçamento?</h3>
          <p className="muted small">
            Sua previsão dos próximos meses (parcelas que você já tem, fixas e gastos planejados) com a parcela nova de {money(r.parcel)}.
          </p>
        </div>
        {projection.isLoading && <p className="muted small">Calculando a previsão…</p>}
        {projection.isError && <p className="tone--error small">Não foi possível carregar a previsão: {errorMessage(projection.error)}</p>}
        {impact && (
          <>
            {impact.partial && (
              <p className="calc-check calc-check--info">
                Previsão parcial: faltam receitas ou meses previstos no período. Cadastre suas receitas fixas para números mais fiéis.
              </p>
            )}
            <div className="calc-impact__stats">
              <div className="calc-ring-card">
                <span
                  className="calc-ring"
                  role="img"
                  aria-label={`Renda comprometida com parcelas: ${impact.committedAfter == null ? "sem receita prevista" : pctText(impact.committedAfter)}`}
                  style={{
                    background: `conic-gradient(var(--fg-ring) 0 ${Math.min(100, impact.committedBefore ?? 0)}%, var(--accent) 0 ${Math.min(100, impact.committedAfter ?? 0)}%, var(--track) 0 100%)`,
                  }}
                >
                  <span className="calc-ring__hole num">{impact.committedAfter == null ? "—" : pctText(Math.round(impact.committedAfter))}</span>
                </span>
                <span className="calc-stat">
                  <span className="calc-stat__label">da renda em parcelas</span>
                  <span className="calc-stat__value num">
                    hoje {impact.committedBefore == null ? "—" : pctText(impact.committedBefore)} → {impact.committedAfter == null ? "—" : pctText(impact.committedAfter)}
                  </span>
                  <span className="calc-stat__hint">
                    {money(impact.installmentsBefore)} → {money(impact.installmentsAfter)} por mês
                  </span>
                </span>
              </div>
              {impact.worst && (
                <Stat
                  label="Mês com menor sobra"
                  value={`${monthLabel(impact.worst.month)} · ${money(impact.worst.after)}`}
                  hint={impact.negativeMonths.length ? `${impact.negativeMonths.length} mês(es) ficam negativos` : "Nenhum mês fica negativo"}
                />
              )}
              <Stat label="Sobra média no período" value={`${money(impact.averageBefore)} → ${money(impact.averageAfter)}`} hint="por mês, antes → depois da compra" />
            </div>

            <div className="calc-bars" tabIndex={0} role="img" aria-label={impact.months.map((x) => `${monthLabel(x.month)}: sobra ${money(x.before)}, com a compra ${money(x.after)}`).join("; ")}>
              {impact.months.map((x) => (
                <div key={x.month} className={`calc-bars__col ${x.after < 0 ? "is-negative" : ""}`}>
                  <div className="calc-bars__pos">
                    <span className="calc-bars__bar calc-bars__bar--before" style={{ height: `${(Math.max(0, x.before) / maxAbs) * 100}%` }} />
                    <span className="calc-bars__bar calc-bars__bar--after" style={{ height: `${(Math.max(0, x.after) / maxAbs) * 100}%` }} />
                  </div>
                  <div className="calc-bars__neg">
                    <span className="calc-bars__bar calc-bars__bar--before" style={{ height: `${(Math.max(0, -x.before) / maxAbs) * 100}%` }} />
                    <span className="calc-bars__bar calc-bars__bar--negative" style={{ height: `${(Math.max(0, -x.after) / maxAbs) * 100}%` }} />
                  </div>
                  <span className="calc-bars__month">{monthLabel(x.month).slice(0, 3)}</span>
                  <span className="calc-bars__value num">{compactValue(x.after, "money")}</span>
                </div>
              ))}
            </div>
            <div className="calc-legend">
              <span>
                <i className="calc-legend__dot calc-legend__dot--before" /> Sobra hoje
              </span>
              <span>
                <i className="calc-legend__dot calc-legend__dot--after" /> Sobra com a compra
              </span>
              <span>
                <i className="calc-legend__dot calc-legend__dot--negative" /> Mês negativo
              </span>
            </div>

            {limit && card && (
              <div className={`calc-check ${limit.fits ? "calc-check--ok" : "calc-check--warn"}`}>
                <div className="split">
                  <span>Limite do {card.card.name}</span>
                  <strong className="num">{pctText(Math.min(999, limit.usedAfterPct))} usado depois da compra</strong>
                </div>
                <span className="calc-compare__track">
                  <span className={`calc-compare__fill calc-compare__fill--${limit.fits ? "accent" : "warn"}`} style={{ width: `${Math.min(100, limit.usedAfterPct)}%` }} />
                </span>
                <span>
                  {limit.fits
                    ? `Cabe: a compra usa ${money(total)} dos ${money(limit.available)} livres. Ficam ${money(limit.freeAfter)}, liberados aos poucos a cada parcela paga.`
                    : `Não cabe: o limite livre é ${money(limit.available)} e a compra ocupa ${money(total)} (faltam ${money(-limit.freeAfter)}).`}
                </span>
              </div>
            )}

            <div className="calc-suggest">
              <p>
                {suggestion
                  ? suggestion === n
                    ? `Com ${n}× nenhum mês fica negativo na sua previsão.`
                    : `Com ${suggestion}× de ${money(total / suggestion)}, nenhum mês fica negativo na sua previsão.`
                  : "Nenhuma opção de até 24× deixa todos os meses positivos na sua previsão."}
              </p>
              <div className="row">
                {suggestion && suggestion !== n && (
                  <Button type="button" onClick={() => setCount(String(suggestion))}>
                    Simular {suggestion}×
                  </Button>
                )}
              </div>
            </div>

            <div className="calc-launch">
              <label className="grow">
                Descrição (para lançar)
                <input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Ex.: Notebook" maxLength={60} />
              </label>
              <Button type="button" variant="secondary" loading={saving} onClick={launch}>
                Lançar como planejado
              </Button>
            </div>
            {saved && (
              <p className="calc-check calc-check--ok" role="status">
                {saved}
              </p>
            )}
            {saveError && (
              <p className="tone--error small" role="alert">
                {saveError}
              </p>
            )}
          </>
        )}
      </section>
    </div>
  );
}

function PrepayCalc() {
  const [parcel, setParcel] = useState("800,00");
  const [count, setCount] = useState("6");
  const [debt, setDebt] = useState("2,5");
  const [invest, setInvest] = useState("0,85");
  const [period, setPeriod] = useState<RatePeriod>("monthly");
  const n = Math.max(1, Math.round(parseNumber(count)) || 1);
  const r = prepay(m(parcel), n, parseNumber(debt), parseNumber(invest || "0,85"), period);
  return (
    <div className="calc-layout">
      <div className="calc-inputs grid-2">
        <label>
          Valor da parcela
          <MoneyInput value={parcel} onChange={setParcel} required={false} />
        </label>
        <Field label="Parcelas a antecipar" unit="parcelas">
          <NumberInput value={count} onChange={setCount} />
        </Field>
        <Field label="Juros da dívida" unit="%">
          <NumberInput value={debt} onChange={setDebt} />
        </Field>
        <Field label="Rendimento da aplicação" unit="%">
          <input inputMode="decimal" value={invest} placeholder="0,85" onChange={(e) => setInvest(onlyNumber(e.target.value))} />
        </Field>
        <label>
          Período das taxas
          <select value={period} onChange={(e) => setPeriod(e.target.value as RatePeriod)}>
            <option value="monthly">Ao mês</option>
            <option value="yearly">Ao ano</option>
          </select>
        </label>
      </div>
      <Hero
        tag={r.better === "prepay" ? "Antecipar compensa" : "Manter aplicado compensa"}
        label="Antecipando, você paga"
        figure={money(r.payNow)}
        chart={
          <Compare
            rows={[
              { label: "Antecipando", value: r.payNow },
              { label: "No vencimento", value: r.nominal, tone: "muted" },
            ]}
          />
        }
      >
        <div className="calc-stats">
          <Stat label="Em vez de" value={money(r.nominal)} />
          <Stat label="Desconto" value={money(r.discount)} />
        </div>
        <p className="calc-note">A taxa da dívida é {r.better === "prepay" ? "maior" : "menor"} que o rendimento da aplicação.</p>
      </Hero>
    </div>
  );
}

function ReserveCalc() {
  const [essential, setEssential] = useState("3.000,00");
  const [months, setMonths] = useState("6");
  const [current, setCurrent] = useState("0,00");
  const r = emergencyFund(m(essential), Math.round(parseNumber(months)), m(current));
  const pct = r.target > 0 ? Math.min(100, (m(current) / r.target) * 100) : 0;
  return (
    <div className="calc-layout">
      <div className="calc-inputs grid-2">
        <label>
          <span className="field-label">
            Gastos essenciais por mês <Tip>Moradia, alimentação, saúde, transporte e contas básicas.</Tip>
          </span>
          <MoneyInput value={essential} onChange={setEssential} required={false} />
        </label>
        <Field label="Meses de cobertura" unit="meses" tip="Referência usual: 3 a 6 meses; para renda variável ou autônomos, 6 a 12.">
          <NumberInput value={months} onChange={setMonths} />
        </Field>
        <label>
          Reserva atual
          <MoneyInput value={current} onChange={setCurrent} required={false} />
        </label>
      </div>
      <Hero
        label="Reserva ideal"
        figure={money(r.target)}
        chart={
          <div className="calc-progress" role="img" aria-label={`Reserva atual cobre ${pct.toFixed(0)}% do ideal`}>
            <span className="calc-compare__track">
              <span className="calc-compare__fill calc-compare__fill--accent" style={{ width: `${pct}%` }} />
            </span>
            <span className="calc-stat__hint">{pctText(Math.round(pct))} do ideal</span>
          </div>
        }
      >
        <div className="calc-stats">
          <Stat label="Falta" value={money(r.missing)} />
          <Stat label="A reserva atual cobre" value={`${r.coverage.toLocaleString("pt-BR")} mês(es)`} />
        </div>
      </Hero>
    </div>
  );
}

function InflationCalc() {
  const [amount, setAmount] = useState("1.000,00");
  const [start, setStart] = useState(addMonths(thisMonth(), -60));
  const [result, setResult] = useState<Inflation | null>(null);
  const [error, setError] = useState("");
  const value = parseMoney(amount);
  useEffect(() => {
    if (!value || !start) return;
    let current = true;
    const timer = window.setTimeout(() => {
      analysisApi
        .inflation(value, start, thisMonth())
        .then((r) => {
          if (!current) return;
          setResult(r);
          setError("");
        })
        .catch((err) => current && setError(errorMessage(err)));
    }, 300);
    return () => {
      current = false;
      window.clearTimeout(timer);
    };
  }, [value, start]);
  return (
    <div className="calc-layout">
      <div className="calc-inputs grid-2">
        <label>
          Valor na época
          <MoneyInput value={amount} onChange={setAmount} required={false} />
        </label>
        <label>
          <span className="field-label">
            Mês do valor <Tip>A correção soma o IPCA de cada mês seguinte até o último divulgado pelo Banco Central.</Tip>
          </span>
          <DateField month value={start} min="1995-01" max={thisMonth()} onChange={setStart} />
        </label>
      </div>
      {error ? (
        <p className="tone--error small" role="alert" style={{ margin: 0 }}>
          {error}
        </p>
      ) : (
        result && (
          <Hero
            label={`Em ${monthLabel(result.end)}, ${money(result.amount)} de ${monthLabel(result.start)} equivalem a`}
            figure={money(result.corrected)}
            chart={
              <Compare
                rows={[
                  { label: "Na época", value: result.amount, tone: "muted" },
                  { label: "Corrigido", value: result.corrected },
                ]}
              />
            }
          >
            <div className="calc-stats">
              <Stat label="Inflação do período (IPCA)" value={pctText(result.inflation_pct)} />
              <Stat label="Meses" value={String(result.months)} />
            </div>
          </Hero>
        )
      )}
    </div>
  );
}

/** v1.4: 13º salário (proporcional aos meses) e a divisão do dinheiro extra. Só números. */
function BonusCalc() {
  const [salary, setSalary] = useState("3.000,00");
  const [months, setMonths] = useState("12");
  const [refund, setRefund] = useState("0,00");
  const [shares, setShares] = useState({ debts: "40", reserve: "30", goals: "30" });
  const gross = (m(salary) * Math.min(Math.max(Math.round(parseNumber(months)), 0), 12)) / 12;
  const total = gross + m(refund);
  const pct = (v: string) => Math.max(0, parseNumber(v));
  const sum = pct(shares.debts) + pct(shares.reserve) + pct(shares.goals);
  const part = (v: string) => (sum > 0 ? (total * pct(v)) / sum : 0);
  return (
    <div className="calc-layout">
      <div className="calc-inputs stack">
        <div className="grid-2">
          <label>
            Salário bruto
            <MoneyInput value={salary} onChange={setSalary} required={false} />
          </label>
          <Field label="Meses trabalhados no ano" unit="meses" tip="Conta o mês com 15 dias ou mais de trabalho.">
            <NumberInput value={months} onChange={setMonths} />
          </Field>
          <label>
            <span className="field-label">
              Restituição do IR esperada <Tip>Opcional. O valor aparece na declaração, depois de enviada.</Tip>
            </span>
            <MoneyInput value={refund} onChange={setRefund} required={false} />
          </label>
        </div>
        <fieldset className="radios">
          <legend className="field-label">Como dividir</legend>
          <div className="grid-3">
            {(
              [
                ["debts", "Dívidas"],
                ["reserve", "Reserva"],
                ["goals", "Metas"],
              ] as const
            ).map(([key, label]) => (
              <Field key={key} label={label} unit="%">
                <NumberInput value={shares[key]} onChange={(v) => setShares((s) => ({ ...s, [key]: v }))} />
              </Field>
            ))}
          </div>
        </fieldset>
      </div>
      <Hero
        label="O extra soma"
        figure={money(total)}
        chart={
          <Compare
            rows={[
              { label: "Dívidas", value: part(shares.debts) },
              { label: "Reserva", value: part(shares.reserve), tone: "muted" },
              { label: "Metas", value: part(shares.goals) },
            ]}
          />
        }
      >
        <div className="calc-stats">
          <Stat label="13º bruto estimado" value={money(gross)} hint={`1ª parcela até 30/11, sem descontos: ${money(gross / 2)}`} />
          <Stat label="Dívidas · Reserva · Metas" value={`${money(part(shares.debts))} · ${money(part(shares.reserve))} · ${money(part(shares.goals))}`} />
        </div>
        <p className="calc-note">A 2ª parcela do 13º, até 20/12, vem com INSS e IR.</p>
      </Hero>
    </div>
  );
}

/** Insights › Ferramentas › Calculadoras: contas rápidas, sem recomendar produtos. */
export function Calculators() {
  const [kind, setKind] = useState<Kind>("cash");
  const cdi = useCdi();
  const current = KINDS.find((k) => k.key === kind)!;
  return (
    <section className="card stack calculators">
      <div className="calc-picker" role="group" aria-label="Calculadora">
        {KINDS.map(({ key, label, short, icon: Icon }) => (
          <button key={key} type="button" className="calc-picker__item" aria-pressed={kind === key} onClick={() => setKind(key)}>
            <Icon size={20} aria-hidden />
            <span className="calc-picker__label">{label}</span>
            <span className="calc-picker__short">{short}</span>
          </button>
        ))}
      </div>
      <p className="muted" style={{ margin: 0 }}>
        {current.text}
      </p>
      <div className="inline-form calc-form">
        {kind === "compound" && <CompoundCalc cdi={cdi} />}
        {kind === "plan" && <PlanCalc cdi={cdi} />}
        {kind === "cash" && <CashCalc cdi={cdi} />}
        {kind === "prepay" && <PrepayCalc />}
        {kind === "reserve" && <ReserveCalc />}
        {kind === "inflation" && <InflationCalc />}
        {kind === "bonus" && <BonusCalc />}
      </div>
      <p className="muted small" style={{ margin: 0 }}>
        Simulações aproximadas, com juros compostos e capitalização mensal, a partir dos seus lançamentos e fixas. Não são recomendação de investimento ou
        de produto financeiro.
      </p>
    </section>
  );
}
