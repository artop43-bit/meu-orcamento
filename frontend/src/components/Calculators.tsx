import { useEffect, useState, type ReactNode } from "react";

import { analysisApi, type Inflation } from "../api/analysis";
import { errorMessage } from "../api/client";
import { DateField } from "./DateField";

import { cashOrInstallments, compound, emergencyFund, prepay, savingPlan, type RatePeriod } from "../lib/calculators";
import { addMonths, money, monthLabel, parseMoney, thisMonth } from "../lib/format";
import { MoneyInput } from "./budget";
import { Tip } from "./help";

type Kind = "compound" | "plan" | "cash" | "prepay" | "reserve" | "inflation" | "bonus";

const KINDS: { key: Kind; label: string; text: string }[] = [
  { key: "compound", label: "Juros compostos", text: "Quanto um valor rende com aportes mensais." },
  { key: "plan", label: "Quanto guardar por mês", text: "O aporte mensal para chegar a um valor numa data." },
  { key: "cash", label: "À vista ou parcelado", text: "Se o desconto à vista compensa o parcelamento sem juros." },
  { key: "prepay", label: "Antecipar parcelas", text: "Antecipar parcelas de uma dívida ou deixar o dinheiro aplicado." },
  { key: "reserve", label: "Reserva de emergência", text: "O valor ideal da reserva a partir dos gastos essenciais." },
  { key: "inflation", label: "Correção pela inflação", text: "Quanto um valor de uma data antiga vale hoje, pelo IPCA do Banco Central." },
  { key: "bonus", label: "13º e restituição", text: "Estimativa do 13º salário e como dividir o dinheiro extra antes de ele chegar." },
];

const num = (v: string) => Number((v || "0").replace(",", "."));
const m = (v: string) => Number(parseMoney(v) ?? 0);

function RateField({ label, value, onChange, period, setPeriod, tip }: { label: string; value: string; onChange: (v: string) => void; period: RatePeriod; setPeriod: (p: RatePeriod) => void; tip?: string }) {
  return (
    <>
      <label>
        <span className="field-label">
          {label} (%) {tip && <Tip>{tip}</Tip>}
        </span>
        <input inputMode="decimal" value={value} onChange={(e) => onChange(e.target.value.replace(/[^\d,.]/g, ""))} />
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

function Result({ children }: { children: ReactNode }) {
  return (
    <div className="calc-result" aria-live="polite">
      {children}
    </div>
  );
}

function CompoundCalc() {
  const [initial, setInitial] = useState("1.000,00");
  const [monthly, setMonthly] = useState("300,00");
  const [rate, setRate] = useState("10,5");
  const [period, setPeriod] = useState<RatePeriod>("yearly");
  const [years, setYears] = useState("5");
  const r = compound(m(initial), m(monthly), num(rate), period, Math.round(num(years) * 12));
  return (
    <>
      <div className="grid-2">
        <label>
          Valor inicial
          <MoneyInput value={initial} onChange={setInitial} required={false} />
        </label>
        <label>
          Aporte por mês
          <MoneyInput value={monthly} onChange={setMonthly} required={false} />
        </label>
        <RateField label="Rendimento" value={rate} onChange={setRate} period={period} setPeriod={setPeriod} tip="Rentabilidade esperada, antes ou depois do imposto: use a mesma base para comparar." />
        <label>
          Prazo (anos)
          <input type="number" min={1} max={60} value={years} onChange={(e) => setYears(e.target.value)} />
        </label>
      </div>
      <Result>
        Em {years} ano(s): <strong>{money(r.final)}</strong>. Você aporta {money(r.invested)} e os juros somam <strong>{money(r.interest)}</strong>.
      </Result>
    </>
  );
}

function PlanCalc() {
  const [target, setTarget] = useState("20.000,00");
  const [current, setCurrent] = useState("0,00");
  const [rate, setRate] = useState("10,5");
  const [period, setPeriod] = useState<RatePeriod>("yearly");
  const [months, setMonths] = useState("24");
  const r = savingPlan(m(target), m(current), num(rate), period, Math.round(num(months)));
  return (
    <>
      <div className="grid-2">
        <label>
          Valor desejado
          <MoneyInput value={target} onChange={setTarget} required={false} />
        </label>
        <label>
          Já guardado
          <MoneyInput value={current} onChange={setCurrent} required={false} />
        </label>
        <RateField label="Rendimento" value={rate} onChange={setRate} period={period} setPeriod={setPeriod} />
        <label>
          Prazo (meses)
          <input type="number" min={1} max={600} value={months} onChange={(e) => setMonths(e.target.value)} />
        </label>
      </div>
      <Result>
        Guarde <strong>{money(r.monthly)}</strong> por mês. Os rendimentos cobrem cerca de {money(r.interest)} do total.
      </Result>
    </>
  );
}

function CashCalc() {
  const [price, setPrice] = useState("3.000,00");
  const [discount, setDiscount] = useState("5");
  const [count, setCount] = useState("10");
  const [rate, setRate] = useState("10,5");
  const [period, setPeriod] = useState<RatePeriod>("yearly");
  const r = cashOrInstallments(m(price), num(discount), Math.max(1, Math.round(num(count))), num(rate), period);
  return (
    <>
      <div className="grid-2">
        <label>
          Preço
          <MoneyInput value={price} onChange={setPrice} required={false} />
        </label>
        <label>
          Desconto à vista (%)
          <input inputMode="decimal" value={discount} onChange={(e) => setDiscount(e.target.value.replace(/[^\d,.]/g, ""))} />
        </label>
        <label>
          Parcelas sem juros
          <input type="number" min={1} max={48} value={count} onChange={(e) => setCount(e.target.value)} />
        </label>
        <RateField label="Rendimento do dinheiro aplicado" value={rate} onChange={setRate} period={period} setPeriod={setPeriod} />
      </div>
      <Result>
        À vista: <strong>{money(r.cash)}</strong>. Parcelado: {count}× de {money(r.parcel)}, equivalente a {money(r.installmentsPresent)} hoje.{" "}
        <strong>{r.better === "cash" ? "À vista sai mais barato" : "Parcelar sai mais barato"}</strong> (diferença de {money(r.difference)}). O
        desconto mínimo para empatar é {r.breakEvenDiscount.toLocaleString("pt-BR")}%.
      </Result>
    </>
  );
}

function PrepayCalc() {
  const [parcel, setParcel] = useState("800,00");
  const [count, setCount] = useState("6");
  const [debt, setDebt] = useState("2,5");
  const [invest, setInvest] = useState("0,85");
  const [period, setPeriod] = useState<RatePeriod>("monthly");
  const r = prepay(m(parcel), Math.max(1, Math.round(num(count))), num(debt), num(invest), period);
  return (
    <>
      <div className="grid-2">
        <label>
          Valor da parcela
          <MoneyInput value={parcel} onChange={setParcel} required={false} />
        </label>
        <label>
          Parcelas a antecipar
          <input type="number" min={1} max={420} value={count} onChange={(e) => setCount(e.target.value)} />
        </label>
        <label>
          Juros da dívida (%)
          <input inputMode="decimal" value={debt} onChange={(e) => setDebt(e.target.value.replace(/[^\d,.]/g, ""))} />
        </label>
        <label>
          Rendimento da aplicação (%)
          <input inputMode="decimal" value={invest} onChange={(e) => setInvest(e.target.value.replace(/[^\d,.]/g, ""))} />
        </label>
        <label>
          Período das taxas
          <select value={period} onChange={(e) => setPeriod(e.target.value as RatePeriod)}>
            <option value="monthly">Ao mês</option>
            <option value="yearly">Ao ano</option>
          </select>
        </label>
      </div>
      <Result>
        Antecipando, você paga <strong>{money(r.payNow)}</strong> em vez de {money(r.nominal)} (desconto de {money(r.discount)}).{" "}
        <strong>{r.better === "prepay" ? "Antecipar compensa" : "Manter o dinheiro aplicado compensa"}</strong>: a taxa da dívida é{" "}
        {r.better === "prepay" ? "maior" : "menor"} que o rendimento da aplicação.
      </Result>
    </>
  );
}

function ReserveCalc() {
  const [essential, setEssential] = useState("3.000,00");
  const [months, setMonths] = useState("6");
  const [current, setCurrent] = useState("0,00");
  const r = emergencyFund(m(essential), Math.round(num(months)), m(current));
  return (
    <>
      <div className="grid-2">
        <label>
          <span className="field-label">
            Gastos essenciais por mês <Tip>Moradia, alimentação, saúde, transporte e contas básicas.</Tip>
          </span>
          <MoneyInput value={essential} onChange={setEssential} required={false} />
        </label>
        <label>
          <span className="field-label">
            Meses de cobertura <Tip>Referência usual: 3 a 6 meses; para renda variável ou autônomos, 6 a 12.</Tip>
          </span>
          <input type="number" min={1} max={24} value={months} onChange={(e) => setMonths(e.target.value)} />
        </label>
        <label>
          Reserva atual
          <MoneyInput value={current} onChange={setCurrent} required={false} />
        </label>
      </div>
      <Result>
        Reserva ideal: <strong>{money(r.target)}</strong>. Falta {money(r.missing)}; a reserva atual cobre {r.coverage.toLocaleString("pt-BR")} mês(es).
      </Result>
    </>
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
    <>
      <div className="grid-2">
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
          <Result>
            {money(result.amount)} em {monthLabel(result.start)} equivalem a <strong>{money(result.corrected)}</strong> em {monthLabel(result.end)}. A
            inflação do período (IPCA) foi de <strong>{result.inflation_pct.toLocaleString("pt-BR")}%</strong> em {result.months} mês(es).
          </Result>
        )
      )}
    </>
  );
}

/** v1.4: 13º salário (proporcional aos meses) e a divisão do dinheiro extra. Só números. */
function BonusCalc() {
  const [salary, setSalary] = useState("3.000,00");
  const [months, setMonths] = useState("12");
  const [refund, setRefund] = useState("0,00");
  const [shares, setShares] = useState({ debts: "40", reserve: "30", goals: "30" });
  const gross = (m(salary) * Math.min(Math.max(Math.round(num(months)), 0), 12)) / 12;
  const total = gross + m(refund);
  const pct = (v: string) => Math.max(0, num(v));
  const sum = pct(shares.debts) + pct(shares.reserve) + pct(shares.goals);
  const part = (v: string) => (sum > 0 ? (total * pct(v)) / sum : 0);
  return (
    <>
      <div className="grid-2">
        <label>
          Salário bruto
          <MoneyInput value={salary} onChange={setSalary} required={false} />
        </label>
        <label>
          <span className="field-label">
            Meses trabalhados no ano <Tip>Conta o mês com 15 dias ou mais de trabalho.</Tip>
          </span>
          <input type="number" min={1} max={12} value={months} onChange={(e) => setMonths(e.target.value)} />
        </label>
        <label>
          <span className="field-label">
            Restituição do IR esperada <Tip>Opcional. O valor aparece na declaração, depois de enviada.</Tip>
          </span>
          <MoneyInput value={refund} onChange={setRefund} required={false} />
        </label>
      </div>
      <fieldset className="radios">
        <legend className="field-label">Como dividir (em %)</legend>
        <div className="grid-3">
          {(
            [
              ["debts", "Dívidas"],
              ["reserve", "Reserva"],
              ["goals", "Metas"],
            ] as const
          ).map(([key, label]) => (
            <label key={key}>
              {label}
              <input type="number" min={0} max={100} value={shares[key]} onChange={(e) => setShares((s) => ({ ...s, [key]: e.target.value }))} />
            </label>
          ))}
        </div>
      </fieldset>
      <Result>
        13º bruto estimado: <strong>{money(gross)}</strong> (1ª parcela até 30/11, sem descontos: {money(gross / 2)}; a 2ª, até 20/12, vem com
        INSS e IR). Com a restituição, o extra soma <strong>{money(total)}</strong>: {money(part(shares.debts))} para dívidas,{" "}
        {money(part(shares.reserve))} para a reserva e {money(part(shares.goals))} para metas.
      </Result>
    </>
  );
}

/** Insights › Ferramentas › Calculadoras: contas rápidas, sem recomendar produtos. */
export function Calculators() {
  const [kind, setKind] = useState<Kind>("compound");
  const current = KINDS.find((k) => k.key === kind)!;
  return (
    <section className="card stack">
      <div className="chips" role="group" aria-label="Calculadora">
        {KINDS.map((k) => (
          <button key={k.key} type="button" className={`chip-btn ${kind === k.key ? "is-active" : ""}`} aria-pressed={kind === k.key} onClick={() => setKind(k.key)}>
            {k.label}
          </button>
        ))}
      </div>
      <p className="muted" style={{ margin: 0 }}>
        {current.text}
      </p>
      <div className="inline-form calc-form">
        {kind === "compound" && <CompoundCalc />}
        {kind === "plan" && <PlanCalc />}
        {kind === "cash" && <CashCalc />}
        {kind === "prepay" && <PrepayCalc />}
        {kind === "reserve" && <ReserveCalc />}
        {kind === "inflation" && <InflationCalc />}
        {kind === "bonus" && <BonusCalc />}
      </div>
      <p className="muted small" style={{ margin: 0 }}>
        Simulações aproximadas, com juros compostos e capitalização mensal. Não são recomendação de investimento ou de produto financeiro.
      </p>
    </section>
  );
}
