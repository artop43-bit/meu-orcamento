import { useMemo, useState } from "react";

import type { Loan, OtherDebt } from "../api/debts";
import { comparePlans, type PayoffDebt, type PayoffResult, type Strategy } from "../lib/payoff";
import { addMonths, money, monthLabel, parseMoney, thisMonth } from "../lib/format";
import { MoneyInput } from "./budget";
import { Tip } from "./help";

const LABELS: Record<Strategy, { title: string; text: string }> = {
  minimum: { title: "Só as parcelas", text: "Sem valor extra" },
  snowball: { title: "Menor dívida primeiro", text: "Quita as pequenas antes; libera parcelas mais cedo" },
  avalanche: { title: "Juros mais altos primeiro", text: "Ataca a dívida mais cara antes" },
};

function when(months: number | null): string {
  if (months === null) return "não termina com essas parcelas";
  if (months === 0) return "já quitado";
  return `${monthLabel(addMonths(thisMonth(), months - 1))} (${months} ${months === 1 ? "mês" : "meses"})`;
}

/**
 * Dívidas › Plano de quitação (v1.3): compara a ordem de pagamento com o mesmo dinheiro por mês.
 * Taxas das "outras dívidas" não ficam salvas: servem só para a simulação.
 */
export function PayoffPlan({ loans, others }: { loans: Loan[]; others: OtherDebt[] }) {
  const [extra, setExtra] = useState("300,00");
  const [rates, setRates] = useState<Record<string, string>>({});
  const debts = useMemo<PayoffDebt[]>(
    () => [
      ...loans
        .filter((l) => Number(l.balance) > 0)
        .map((l) => ({
          id: l.id,
          name: l.name,
          balance: Number(l.balance),
          rate: l.monthly_rate / 100,
          kind: l.system,
          remaining: Math.max(l.installments - l.paid_installments, 1),
        })),
      ...others
        .filter((d) => Number(d.balance) > 0)
        .map((d) => ({
          id: d.id,
          name: d.name,
          balance: Number(d.balance),
          rate: Number((rates[d.id] ?? "0").replace(",", ".")) / 100 || 0,
          kind: "fixed" as const,
          payment: Number(d.monthly_payment ?? 0),
        })),
    ],
    [loans, others, rates],
  );
  const extraValue = Number(parseMoney(extra) ?? 0);
  const plans = useMemo(() => comparePlans(debts, extraValue), [debts, extraValue]);
  if (debts.length === 0) return null;
  const best = (["snowball", "avalanche"] as Strategy[]).reduce((a, b) => (plans[b].interest < plans[a].interest ? b : a));
  const saved = plans.minimum.months !== null ? plans.minimum.interest - plans[best].interest : null;

  return (
    <section className="card stack payoff" aria-labelledby="plano-quitacao">
      <div>
        <h2 id="plano-quitacao">Plano de quitação</h2>
        <p className="muted small" style={{ margin: 0 }}>
          Compara duas ordens de pagamento com o mesmo dinheiro por mês: as parcelas de hoje mais um valor extra. Quando uma dívida termina,
          a parcela dela passa para a próxima.
        </p>
      </div>
      <div className="grid-2">
        <label>
          <span className="field-label">
            Valor extra por mês <Tip>Quanto você consegue pagar além das parcelas. O extra vai inteiro para a dívida da vez.</Tip>
          </span>
          <MoneyInput value={extra} onChange={setExtra} required={false} />
        </label>
        {others
          .filter((d) => Number(d.balance) > 0)
          .map((d) => (
            <label key={d.id}>
              <span className="field-label">
                Juros de “{d.name}” (% a.m.) <Tip>Opcional, só para esta simulação. Sem taxa, a dívida é tratada como sem juros.</Tip>
              </span>
              <input
                inputMode="decimal"
                value={rates[d.id] ?? ""}
                placeholder="0"
                onChange={(e) => setRates((r) => ({ ...r, [d.id]: e.target.value }))}
              />
            </label>
          ))}
      </div>
      <div className="payoff__plans">
        {(Object.keys(LABELS) as Strategy[]).map((key) => (
          <PlanCard key={key} plan={plans[key]} highlight={key === best && extraValue > 0} />
        ))}
      </div>
      {saved !== null && saved > 0.5 && extraValue > 0 && (
        <p className="summary-box" style={{ margin: 0 }}>
          Com {money(extraValue)} extras por mês, a ordem “{LABELS[best].title.toLowerCase()}” paga <strong>{money(saved)}</strong> a menos de
          juros do que só as parcelas.
        </p>
      )}
      <p className="muted small" style={{ margin: 0 }}>
        Simulação com as taxas e saldos de hoje e juros compostos ao mês. Seguro e taxas mensais não entram. Não é recomendação de produto
        financeiro.
      </p>
    </section>
  );
}

function PlanCard({ plan, highlight }: { plan: PayoffResult; highlight: boolean }) {
  const label = LABELS[plan.strategy];
  return (
    <article className={`payoff__plan ${highlight ? "is-best" : ""}`}>
      <h3>
        {label.title}
        {highlight && <span className="badge badge--accent">menos juros</span>}
      </h3>
      <p className="muted small">{label.text}</p>
      <dl>
        <div>
          <dt>Quitação total</dt>
          <dd>{when(plan.months)}</dd>
        </div>
        <div>
          <dt>Juros pagos</dt>
          <dd>{money(plan.interest)}</dd>
        </div>
      </dl>
      {plan.finished.length > 0 && (
        <ol className="payoff__order">
          {plan.finished.map((f) => (
            <li key={f.id}>
              {f.name} <span className="muted">· {monthLabel(addMonths(thisMonth(), f.month - 1), true)}</span>
            </li>
          ))}
        </ol>
      )}
    </article>
  );
}
