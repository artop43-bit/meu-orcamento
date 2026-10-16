import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";

import {
  analysisApi,
  INVESTMENT_KINDS,
  type Investment,
  type InvestmentKind,
} from "../api/analysis";
import { useBudgetMutation } from "../api/budget";
import { errorMessage } from "../api/client";
import { Badge, Bar, FormActions, MoneyInput, requireMoney } from "../components/budget";
import { Alert, Button } from "../components/ui";
import { money, moneyInput, parseMoney, percent } from "../lib/format";

const KEY = ["budget", "investments"] as const;
const KIND_COLORS: Record<InvestmentKind, string> = {
  poupanca: "#bab0ac",
  renda_fixa: "#4e79a7",
  tesouro: "#59a14f",
  fundos: "#76b7b2",
  acoes: "#f28e2b",
  fiis: "#9c755f",
  cripto: "#b07aa1",
  previdencia: "#e15759",
  outro: "#79706e",
};

function Indicators() {
  const indicators = useQuery({
    queryKey: ["indicators"],
    queryFn: analysisApi.indicators,
    staleTime: 3_600_000,
  });
  const data = indicators.data;
  const item = (label: string, value: { value: number; date: string } | null | undefined, suffix: string) => (
    <div className="stat">
      <span className="stat__label">{label}</span>
      <strong className="stat__value">
        {value ? `${value.value.toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%` : "—"}
      </strong>
      <span className="muted small">{value ? `${suffix} · ${value.date}` : suffix}</span>
    </div>
  );

  return (
    <section className="card stack">
      <div className="section-header">
        <h2>Indicadores</h2>
        <span className="muted small">Fonte: Banco Central do Brasil</span>
      </div>
      {indicators.isError && <Alert tone="error">{errorMessage(indicators.error)}</Alert>}
      {data && !data.available && (
        <Alert tone="info">Não foi possível consultar o Banco Central agora. Tente mais tarde.</Alert>
      )}
      <div className="stats">
        {item("Selic", data?.selic, "meta ao ano")}
        {item("CDI", data?.cdi, "ao ano")}
        {item("IPCA", data?.ipca_12m, "últimos 12 meses")}
      </div>
    </section>
  );
}

function InvestmentForm({ investment, onDone }: { investment?: Investment; onDone: () => void }) {
  const [name, setName] = useState(investment?.name ?? "");
  const [kind, setKind] = useState<InvestmentKind>(investment?.kind ?? "renda_fixa");
  const [institution, setInstitution] = useState(investment?.institution ?? "");
  const [invested, setInvested] = useState(investment ? moneyInput(investment.invested_amount) : "");
  const [current, setCurrent] = useState(investment ? moneyInput(investment.current_value) : "");
  const [reserve, setReserve] = useState(investment?.is_emergency_reserve ?? false);
  const [error, setError] = useState("");

  const save = useBudgetMutation(async () => {
    const investedValue = parseMoney(invested);
    if (investedValue === null) throw new Error("Informe quanto você investiu.");
    // Valor atual em branco = igual ao investido.
    const currentValue = current.trim() ? requireMoney(current) : investedValue;
    const data = {
      name,
      kind,
      institution: institution.trim() || null,
      invested_amount: investedValue,
      current_value: currentValue,
      is_emergency_reserve: reserve,
    };
    if (investment) await analysisApi.updateInvestment(investment.id, data);
    else await analysisApi.createInvestment(data);
  });

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      await save.mutateAsync(undefined);
      onDone();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <form className="inline-form" onSubmit={submit}>
      <Alert tone="error">{error}</Alert>
      <div className="grid-2">
        <label>
          Nome
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="CDB 110% CDI" required maxLength={80} autoFocus />
        </label>
        <label>
          Tipo
          <select value={kind} onChange={(e) => setKind(e.target.value as InvestmentKind)}>
            {Object.entries(INVESTMENT_KINDS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Instituição (opcional)
          <input value={institution} onChange={(e) => setInstitution(e.target.value)} placeholder="Banco, corretora…" maxLength={80} />
        </label>
        <label>
          Quanto investiu
          <MoneyInput value={invested} onChange={setInvested} />
        </label>
        <label>
          Valor atual
          <input inputMode="decimal" placeholder="Igual ao investido" value={current} onChange={(e) => setCurrent(e.target.value)} />
        </label>
      </div>
      <label className="check">
        <input type="checkbox" checked={reserve} onChange={(e) => setReserve(e.target.checked)} />
        Faz parte da minha reserva de emergência
      </label>
      <FormActions loading={save.isPending} onCancel={onDone} label={investment ? "Salvar" : "Adicionar"} />
    </form>
  );
}

function InvestmentRow({ investment }: { investment: Investment }) {
  const [editing, setEditing] = useState(false);
  const remove = useBudgetMutation(() => analysisApi.deleteInvestment(investment.id));
  const ret = Number(investment.return_amount);

  if (editing) {
    return (
      <li>
        <InvestmentForm investment={investment} onDone={() => setEditing(false)} />
      </li>
    );
  }
  return (
    <li className="item">
      <button type="button" className="item__main" onClick={() => setEditing(true)} title="Editar">
        <span className="item__title">
          <span className="dot" style={{ background: KIND_COLORS[investment.kind] }} aria-hidden />
          {investment.name}
        </span>
        <span className="item__meta">
          {INVESTMENT_KINDS[investment.kind]}
          {investment.institution && ` · ${investment.institution}`}
          {" · investido "}
          {money(investment.invested_amount)}
        </span>
      </button>
      {investment.is_emergency_reserve && (
        <span className="item__badges">
          <Badge tone="accent">reserva</Badge>
        </span>
      )}
      <span className="item__value">
        <strong className="item__amount">{money(investment.current_value)}</strong>
        <span className={`small ${ret > 0 ? "tone--ok" : ret < 0 ? "tone--error" : "muted"}`}>
          {ret > 0 ? "+" : ""}
          {money(ret)}
          {investment.return_pct !== null && ` (${percent(investment.return_pct)})`}
        </span>
      </span>
      <button
        type="button"
        className="icon-btn"
        aria-label="Excluir"
        title="Excluir"
        onClick={() => window.confirm(`Excluir "${investment.name}"?`) && remove.mutate(undefined)}
      >
        ✕
      </button>
    </li>
  );
}

export default function Investments() {
  const list = useQuery({ queryKey: KEY, queryFn: analysisApi.investments });
  const [adding, setAdding] = useState(false);
  const items = list.data ?? [];

  const invested = items.reduce((s, i) => s + Number(i.invested_amount), 0);
  const current = items.reduce((s, i) => s + Number(i.current_value), 0);
  const reserve = items.filter((i) => i.is_emergency_reserve).reduce((s, i) => s + Number(i.current_value), 0);
  const byKind = Object.entries(
    items.reduce<Record<string, number>>((acc, i) => {
      acc[i.kind] = (acc[i.kind] ?? 0) + Number(i.current_value);
      return acc;
    }, {}),
  ).sort((a, b) => b[1] - a[1]);

  return (
    <div className="stack">
      <div className="section-header">
        <h1>Investimentos</h1>
        {!adding && (
          <Button type="button" onClick={() => setAdding(true)}>
            + Investimento
          </Button>
        )}
      </div>

      <Indicators />

      {list.isError && <Alert tone="error">{errorMessage(list.error)}</Alert>}

      {items.length > 0 && (
        <section className="card stack">
          <div className="stats">
            <div className="stat">
              <span className="stat__label">Patrimônio</span>
              <strong className="stat__value">{money(current)}</strong>
            </div>
            <div className="stat">
              <span className="stat__label">Rendimento</span>
              <strong className={`stat__value ${current - invested < 0 ? "tone--error" : "tone--ok"}`}>
                {money(current - invested)}
              </strong>
              {invested > 0 && <span className="muted small">{percent(Math.round(((current - invested) / invested) * 1000) / 10)}</span>}
            </div>
            <div className="stat">
              <span className="stat__label">Reserva de emergência</span>
              <strong className="stat__value">{money(reserve)}</strong>
            </div>
          </div>
          <ul className="breakdown">
            {byKind.map(([kind, value]) => (
              <li key={kind}>
                <div className="split">
                  <span>{INVESTMENT_KINDS[kind as InvestmentKind]}</span>
                  <span>
                    {money(value)} <span className="muted">· {percent(Math.round((value / current) * 1000) / 10)}</span>
                  </span>
                </div>
                <Bar pct={current > 0 ? (value / current) * 100 : 0} color={KIND_COLORS[kind as InvestmentKind]} />
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="card stack">
        <h2>Carteira</h2>
        {adding && <InvestmentForm onDone={() => setAdding(false)} />}
        {list.isPending && <p className="muted">Carregando…</p>}
        {items.length === 0 && !adding && !list.isPending && (
          <p className="muted">
            Cadastre onde seu dinheiro está guardado. Marque o que é reserva de emergência para que conte no seu
            score financeiro.
          </p>
        )}
        <ul className="items">
          {items.map((i) => (
            <InvestmentRow key={i.id} investment={i} />
          ))}
        </ul>
        <p className="muted small">
          Os valores atuais são informados por você. Atualize de tempos em tempos com o saldo do banco ou da
          corretora.
        </p>
      </section>
    </div>
  );
}
