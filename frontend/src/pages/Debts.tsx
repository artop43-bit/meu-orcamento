import { useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Calculator, FileSpreadsheet, HandCoins, Landmark, Pencil, Plus, Scale, Trash2, TrendingDown, Wallet } from "lucide-react";
import { Link } from "react-router";

import { useCategories } from "../api/budget";
import { errorMessage } from "../api/client";
import { DEBTS_KEY, debtsApi, LOAN_KINDS, type ExtraResult, type Loan, type LoanInput, type LoanKind, type OtherDebt } from "../api/debts";
import { useAccounts } from "../api/money";
import { Bar, CategorySelect, MoneyInput, requireMoney } from "../components/budget";
import { Chart } from "../components/chart/Chart";
import { DateField } from "../components/DateField";
import { EmptyGuide, Tip } from "../components/help";
import { Alert, Button, Kpi, LoadingRegion, PageHeader, Sheet, Skeleton } from "../components/ui";
import { useUndo } from "../components/undo";
import { announce } from "../lib/announce";
import { loanPreview } from "../lib/calculators";
import { money, moneyInput, monthLabel, parseMoney, shortDate, thisMonth } from "../lib/format";

const rate = (v: number) => `${v.toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%`;

/** Parcelas já vencidas pela data da 1ª parcela (sugestão para contratos em andamento). */
function elapsed(firstDue: string): number {
  if (!firstDue) return 0;
  const [y, m, d] = firstDue.split("-").map(Number);
  const today = new Date();
  let months = (today.getFullYear() - y!) * 12 + (today.getMonth() + 1 - m!);
  if (today.getDate() >= d!) months += 1;
  return Math.max(0, months);
}

function LoanForm({ loan, onDone }: { loan?: Loan; onDone: () => void }) {
  const queryClient = useQueryClient();
  const categories = useCategories();
  const accounts = useAccounts();
  const [kind, setKind] = useState<LoanKind>(loan?.kind ?? "personal");
  const [name, setName] = useState(loan?.name ?? "");
  const [institution, setInstitution] = useState(loan?.institution ?? "");
  const [principal, setPrincipal] = useState(loan ? moneyInput(loan.principal) : "");
  const [ratePct, setRatePct] = useState(loan ? String(Number(loan.rate)).replace(".", ",") : "");
  const [period, setPeriod] = useState<"monthly" | "yearly">(loan?.rate_period ?? "monthly");
  const [system, setSystem] = useState<"price" | "sac">(loan?.system ?? "price");
  const [count, setCount] = useState(loan ? String(loan.installments) : "");
  const [firstDue, setFirstDue] = useState(loan?.first_due ?? "");
  const [paidBefore, setPaidBefore] = useState(loan ? String(loan.paid_before) : "0");
  const [insurance, setInsurance] = useState(loan ? moneyInput(loan.insurance_monthly) : "");
  const [fee, setFee] = useState(loan ? moneyInput(loan.fee_monthly) : "");
  const [iof, setIof] = useState(loan ? moneyInput(loan.iof) : "");
  const [category, setCategory] = useState(loan?.category_id ?? "");
  const [account, setAccount] = useState(loan?.account_id ?? "");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const rateNumber = Number((ratePct || "0").replace(",", "."));
  const extras = Number(parseMoney(insurance) ?? 0) + Number(parseMoney(fee) ?? 0);
  const preview = loanPreview(Number(parseMoney(principal) ?? 0) + Number(parseMoney(iof) ?? 0), rateNumber, period, Number(count), system, extras);
  const suggested = Math.min(elapsed(firstDue), Math.max(0, Number(count) - 1));

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    const data: LoanInput = {
      kind,
      name: name.trim(),
      institution: institution.trim() || null,
      principal: requireMoney(principal),
      rate: String(rateNumber),
      rate_period: period,
      system,
      installments: Number(count),
      first_due: firstDue,
      paid_before: Number(paidBefore || 0),
      insurance_monthly: parseMoney(insurance) ?? "0",
      fee_monthly: parseMoney(fee) ?? "0",
      iof: parseMoney(iof) ?? "0",
      category_id: category || null,
      account_id: account || null,
      notes: loan?.notes ?? null,
    };
    try {
      if (loan) await debtsApi.updateLoan(loan.id, data);
      else await debtsApi.createLoan(data);
      announce(loan ? "Financiamento atualizado" : "Financiamento cadastrado; as parcelas entraram no orçamento");
      await queryClient.invalidateQueries({ queryKey: DEBTS_KEY });
      await queryClient.invalidateQueries({ queryKey: ["budget"] });
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
      <div className="grid-2">
        <label>
          Tipo
          <select value={kind} onChange={(e) => setKind(e.target.value as LoanKind)}>
            {LOAN_KINDS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Nome
          <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={80} placeholder="Ex.: Financiamento do apartamento" />
        </label>
        <label>
          Instituição (opcional)
          <input value={institution} onChange={(e) => setInstitution(e.target.value)} maxLength={80} placeholder="Ex.: Caixa" />
        </label>
        <label>
          Valor financiado
          <MoneyInput value={principal} onChange={setPrincipal} />
        </label>
      </div>
      <div className="grid-2">
        <label>
          <span className="field-label">
            Taxa de juros (%) <Tip>A taxa do contrato. Se vier ao ano, o app converte para ao mês por juros compostos.</Tip>
          </span>
          <input value={ratePct} onChange={(e) => setRatePct(e.target.value.replace(/[^\d,.]/g, ""))} inputMode="decimal" required placeholder="Ex.: 1,49" />
        </label>
        <label>
          Número de parcelas
          <input type="number" min={1} max={420} value={count} onChange={(e) => setCount(e.target.value)} required />
        </label>
      </div>
      <fieldset className="radios">
        <legend className="field-label">Período da taxa</legend>
        <div className="segmented">
          <label>
            <input type="radio" name="rate-period" checked={period === "monthly"} onChange={() => setPeriod("monthly")} />
            Ao mês
          </label>
          <label>
            <input type="radio" name="rate-period" checked={period === "yearly"} onChange={() => setPeriod("yearly")} />
            Ao ano
          </label>
        </div>
      </fieldset>
      <fieldset className="radios">
        <legend className="field-label">
          Sistema de amortização{" "}
          <Tip>Price: parcelas iguais (comum em empréstimos e veículos). SAC: a parcela começa maior e cai todo mês (comum em imóveis).</Tip>
        </legend>
        <div className="segmented">
          <label>
            <input type="radio" name="loan-system" checked={system === "price"} onChange={() => setSystem("price")} />
            Price (parcelas iguais)
          </label>
          <label>
            <input type="radio" name="loan-system" checked={system === "sac"} onChange={() => setSystem("sac")} />
            SAC (parcelas que caem)
          </label>
        </div>
      </fieldset>
      <div className="grid-2">
        <label>
          Vencimento da 1ª parcela
          <DateField value={firstDue} onChange={setFirstDue} required />
        </label>
        <label>
          <span className="field-label">
            Parcelas já pagas <Tip>Para um contrato em andamento: as parcelas pagas antes de cadastrar no app não entram no orçamento.</Tip>
          </span>
          <input type="number" min={0} max={419} value={paidBefore} onChange={(e) => setPaidBefore(e.target.value)} />
        </label>
      </div>
      {suggested > 0 && Number(paidBefore || 0) !== suggested && (
        <p className="muted small" style={{ margin: 0 }}>
          Pelas datas, {suggested} parcela(s) já venceram.{" "}
          <button type="button" className="link-btn" onClick={() => setPaidBefore(String(suggested))}>
            Usar {suggested}
          </button>
        </p>
      )}
      <details className="details">
        <summary>Custos extras (opcional)</summary>
        <div className="grid-2">
          <label>
            Seguro por mês
            <MoneyInput value={insurance} onChange={setInsurance} required={false} />
          </label>
          <label>
            Taxa de administração por mês
            <MoneyInput value={fee} onChange={setFee} required={false} />
          </label>
          <label>
            IOF somado ao valor financiado
            <MoneyInput value={iof} onChange={setIof} required={false} />
          </label>
        </div>
      </details>
      <div className="grid-2">
        <label>
          Categoria das parcelas
          <CategorySelect categories={categories.data ?? []} value={category} onChange={setCategory} />
        </label>
        <label>
          Conta de pagamento (opcional)
          <select value={account} onChange={(e) => setAccount(e.target.value)}>
            <option value="">Sem conta</option>
            {(accounts.data ?? []).map((b) => (
              <option key={b.account.id} value={b.account.id}>
                {b.account.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      {preview && rateNumber >= 0 && (
        <p className="summary-box" aria-live="polite">
          {system === "price" ? (
            <>
              Parcela de <strong>{money(preview.first)}</strong>
            </>
          ) : (
            <>
              Parcelas de <strong>{money(preview.first)}</strong> caindo até <strong>{money(preview.last)}</strong>
            </>
          )}
          ; juros no contrato: <strong>{money(preview.interest)}</strong>.
        </p>
      )}
      <p className="muted small" style={{ margin: 0 }}>
        As parcelas a pagar entram no Orçamento de cada mês como despesas. Ao marcar uma como paga, o saldo devedor diminui.
      </p>
      <div className="form-actions">
        <Button type="button" variant="secondary" onClick={onDone}>
          Cancelar
        </Button>
        <Button type="submit" loading={busy}>
          {loan ? "Salvar" : "Cadastrar"}
        </Button>
      </div>
    </form>
  );
}

function ExtraSimulation({ loan }: { loan: Loan }) {
  const [amount, setAmount] = useState("");
  const [mode, setMode] = useState<"term" | "payment">("term");
  const [result, setResult] = useState<ExtraResult | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      setResult(await debtsApi.simulate(loan.id, { amount: requireMoney(amount), mode }));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="inline-form" onSubmit={submit}>
      <p className="muted small" style={{ margin: 0 }}>
        Saldo devedor hoje: <strong>{money(loan.balance)}</strong>. A simulação não altera o contrato.
      </p>
      <Alert tone="error">{error}</Alert>
      <label>
        Valor a amortizar
        <MoneyInput value={amount} onChange={setAmount} />
      </label>
      <fieldset className="radios">
        <legend className="field-label">Depois de amortizar</legend>
        <div className="segmented">
          <label>
            <input type="radio" name="extra-mode" checked={mode === "term"} onChange={() => setMode("term")} />
            Reduzir o prazo
          </label>
          <label>
            <input type="radio" name="extra-mode" checked={mode === "payment"} onChange={() => setMode("payment")} />
            Reduzir a parcela
          </label>
        </div>
      </fieldset>
      {result && (
        <div className="summary-box" aria-live="polite">
          <strong>Economia de {money(result.interest_saved)} em juros.</strong>
          <br />
          {result.mode === "term"
            ? `Prazo cai de ${result.months_before} para ${result.months_after} parcelas${result.end_after ? `; termina em ${monthLabel(result.end_after.slice(0, 7))}` : ""}.`
            : `Parcela cai de ${money(result.payment_before)} para ${money(result.payment_after)}, mantendo ${result.months_after} parcelas.`}
        </div>
      )}
      <div className="form-actions">
        <Button type="submit" loading={busy}>
          Simular
        </Button>
      </div>
    </form>
  );
}

function LoanCard({ loan, onEdit, onRemove }: { loan: Loan; onEdit: () => void; onRemove: () => void }) {
  const [simulating, setSimulating] = useState(false);
  const progress = (loan.paid_installments / loan.installments) * 100;
  const done = loan.paid_installments >= loan.installments;
  return (
    <section className="card stack loan-card">
      <div className="section-header">
        <span className="loan-card__title">
          <span className="kpi__icon" aria-hidden>
            <Landmark size={18} />
          </span>
          <span>
            <h2>{loan.name}</h2>
            <span className="muted small">
              {loan.kind_label}
              {loan.institution && ` · ${loan.institution}`} · {loan.system === "price" ? "Price" : "SAC"}
            </span>
          </span>
        </span>
        <span className="row" style={{ gap: 0, flexWrap: "nowrap" }}>
          <button type="button" className="icon-btn" aria-label={`Editar ${loan.name}`} title="Editar" onClick={onEdit}>
            <Pencil size={16} />
          </button>
          <button type="button" className="icon-btn" aria-label={`Excluir ${loan.name}`} title="Excluir" onClick={onRemove}>
            <Trash2 size={16} />
          </button>
        </span>
      </div>
      <div className="split" style={{ alignItems: "baseline" }}>
        <span>
          <span className="muted small">Saldo devedor</span>
          <br />
          <span className="kpi__value">{money(loan.balance)}</span>
        </span>
        <span className="muted small" style={{ textAlign: "right" }}>
          {loan.paid_installments} de {loan.installments} parcelas
          <br />
          até {monthLabel(loan.end.slice(0, 7))}
        </span>
      </div>
      <Bar pct={progress} />
      <dl className="loan-card__facts">
        <div>
          <dt>Próxima parcela</dt>
          <dd>{loan.next_payment ? `${money(loan.next_payment)} em ${shortDate(loan.next_due)}` : "Quitado"}</dd>
        </div>
        <div>
          <dt>Taxa</dt>
          <dd>
            {rate(loan.monthly_rate)} a.m. · {rate(loan.yearly_rate)} a.a.
          </dd>
        </div>
        <div>
          <dt>
            Custo efetivo (CET) <Tip>Considera juros, seguro, taxas e IOF: é o custo real do contrato.</Tip>
          </dt>
          <dd>{rate(loan.cet_yearly)} a.a.</dd>
        </div>
        <div>
          <dt>Juros no contrato</dt>
          <dd>{money(loan.total_interest)}</dd>
        </div>
      </dl>
      <div className="loan-card__actions">
        <Link className="btn btn--secondary" to={`/dividas/${loan.id}/tabela`}>
          <FileSpreadsheet size={16} aria-hidden /> Tabela de parcelas
        </Link>
        {!done && (
          <Button type="button" variant="secondary" onClick={() => setSimulating(true)}>
            <TrendingDown size={16} /> Simular amortização extra
          </Button>
        )}
      </div>
      <Sheet open={simulating} title={`Amortização extra · ${loan.name}`} onClose={() => setSimulating(false)}>
        {simulating && <ExtraSimulation loan={loan} />}
      </Sheet>
    </section>
  );
}

function OtherDebtForm({ debt, onDone }: { debt?: OtherDebt; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(debt?.name ?? "");
  const [balance, setBalance] = useState(debt ? moneyInput(debt.balance) : "");
  const [monthly, setMonthly] = useState(debt?.monthly_payment ? moneyInput(debt.monthly_payment) : "");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    const data = { name: name.trim(), balance: parseMoney(balance) ?? "0", monthly_payment: parseMoney(monthly), notes: debt?.notes ?? null };
    try {
      if (debt) await debtsApi.updateOther(debt.id, data);
      else await debtsApi.createOther(data);
      await queryClient.invalidateQueries({ queryKey: DEBTS_KEY });
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
      <label>
        Nome
        <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={80} placeholder="Ex.: Acordo com o banco" />
      </label>
      <div className="grid-2">
        <label>
          Saldo devedor
          <MoneyInput value={balance} onChange={setBalance} />
        </label>
        <label>
          Pagamento por mês (opcional)
          <MoneyInput value={monthly} onChange={setMonthly} required={false} />
        </label>
      </div>
      <p className="muted small" style={{ margin: 0 }}>
        Para dívidas sem tabela (acordos, empréstimo com família). Atualize o saldo quando pagar.
      </p>
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

export default function DebtsPage() {
  const queryClient = useQueryClient();
  const overview = useQuery({ queryKey: DEBTS_KEY, queryFn: debtsApi.overview });
  const undo = useUndo();
  const [editing, setEditing] = useState<Loan | "new" | null>(null);
  const [other, setOther] = useState<OtherDebt | "new" | null>(null);
  const data = overview.data;
  const loans = (data?.loans ?? []).filter((l) => !undo.isHidden(l.id));
  const others = (data?.others ?? []).filter((d) => !undo.isHidden(d.id));
  const empty = data && data.loans.length === 0 && data.others.length === 0 && Number(data.card_installments) === 0;

  function removeLoan(loan: Loan) {
    undo.remove({
      ids: [loan.id],
      message: `"${loan.name}" excluído (as parcelas já pagas ficam no histórico)`,
      commit: async () => {
        await debtsApi.deleteLoan(loan.id);
        await queryClient.invalidateQueries({ queryKey: DEBTS_KEY });
      },
    });
  }

  function removeOther(debt: OtherDebt) {
    undo.remove({
      ids: [debt.id],
      message: `"${debt.name}" excluída`,
      commit: async () => {
        await debtsApi.deleteOther(debt.id);
        await queryClient.invalidateQueries({ queryKey: DEBTS_KEY });
      },
    });
  }

  const history = data?.history ?? [];
  return (
    <>
      <PageHeader
        title="Dívidas"
        subtitle="Financiamentos, empréstimos e outras dívidas, com o patrimônio líquido mês a mês."
        actions={
          <Button type="button" onClick={() => setEditing("new")}>
            <Plus size={16} /> Novo financiamento
          </Button>
        }
      />
      {overview.isPending && (
        <LoadingRegion label="Carregando as dívidas">
          <Skeleton height={220} />
        </LoadingRegion>
      )}
      {overview.isError && <Alert tone="error">{errorMessage(overview.error)}</Alert>}
      {data && (
        <div className="kpis" style={{ marginBottom: 20 }}>
          <Kpi icon={<Scale size={18} />} tone="expense" label="Dívida total" value={money(data.debts)} foot="Saldos devedores e parcelas futuras do cartão" />
          <Kpi icon={<Wallet size={18} />} tone="neutral" label="Parcelas por mês" value={money(data.monthly_payments)} foot="Financiamentos e outras dívidas" />
          <Kpi icon={<HandCoins size={18} />} tone="neutral" label="Bens e investimentos" value={money(data.assets)} foot={`Contas ${money(data.accounts)} · investimentos ${money(data.investments)}`} />
          <Kpi
            icon={<Landmark size={18} />}
            label="Patrimônio líquido"
            value={money(data.net_worth)}
            valueClass={Number(data.net_worth) >= 0 ? "tone--ok" : "tone--error"}
            foot="Bens e investimentos menos dívidas"
          />
        </div>
      )}
      {data && (
        <section className="card stack" style={{ marginBottom: 20 }}>
          <h2>Patrimônio líquido mês a mês</h2>
          {history.length >= 2 ? (
            <Chart
              type="area"
              labels={history.map((h) => ({ key: h.month.slice(0, 7), label: h.month.slice(0, 7) }))}
              series={[
                { key: "net", name: "Patrimônio líquido", color: "var(--accent)", values: history.map((h) => Number(h.net)) },
                { key: "debts", name: "Dívidas", color: "var(--expense)", values: history.map((h) => Number(h.debts)) },
              ]}
              monthLabels
              height={220}
              description="Patrimônio líquido e dívidas por mês"
            />
          ) : (
            <p className="muted" style={{ margin: 0 }}>
              O gráfico ganha um ponto por mês a partir de {monthLabel(history[0]?.month.slice(0, 7) ?? thisMonth()).toLowerCase()}. Volte no
              próximo mês para ver a evolução.
            </p>
          )}
        </section>
      )}
      {empty && (
        <section className="card">
          <EmptyGuide
            icon={<Landmark size={22} />}
            title="Nenhuma dívida cadastrada"
            text="Cadastre financiamentos e empréstimos com a taxa do contrato: o app calcula as parcelas, lança no Orçamento e acompanha o saldo devedor."
            action={
              <Button type="button" onClick={() => setEditing("new")}>
                <Plus size={16} /> Cadastrar financiamento
              </Button>
            }
          />
        </section>
      )}
      {loans.length > 0 && (
        <div className="grid-cards" style={{ marginBottom: 20 }}>
          {loans.map((loan) => (
            <LoanCard key={loan.id} loan={loan} onEdit={() => setEditing(loan)} onRemove={() => removeLoan(loan)} />
          ))}
        </div>
      )}
      {data && !empty && (
        <div className="layout-2">
          <section className="card stack">
            <div className="section-header">
              <h2>Outras dívidas</h2>
              <Button type="button" variant="secondary" onClick={() => setOther("new")}>
                <Plus size={16} /> Adicionar
              </Button>
            </div>
            {others.length === 0 ? (
              <p className="muted" style={{ margin: 0 }}>
                Acordos e dívidas sem tabela de parcelas.
              </p>
            ) : (
              <ul className="items">
                {others.map((d) => (
                  <li key={d.id} className="item">
                    <span className="item__main">
                      <span className="item__title">{d.name}</span>
                      <span className="item__meta">{d.monthly_payment ? `${money(d.monthly_payment)} por mês` : "Sem pagamento mensal"}</span>
                    </span>
                    <strong className="num">{money(d.balance)}</strong>
                    <button type="button" className="icon-btn" aria-label={`Editar ${d.name}`} onClick={() => setOther(d)}>
                      <Pencil size={16} />
                    </button>
                    <button type="button" className="icon-btn" aria-label={`Excluir ${d.name}`} onClick={() => removeOther(d)}>
                      <Trash2 size={16} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section className="card stack">
            <h2>Parcelas futuras do cartão</h2>
            <p className="kpi__value" style={{ margin: 0 }}>
              {money(data.card_installments)}
            </p>
            <p className="muted small" style={{ margin: 0 }}>
              Compras parceladas que ainda vão chegar nas próximas faturas. Já entram na dívida total.
            </p>
            <div>
              <Link className="btn btn--secondary" to="/analises?secao=calculadoras">
                <Calculator size={16} aria-hidden /> Calculadoras
              </Link>
            </div>
          </section>
        </div>
      )}
      <Sheet open={editing !== null} title={editing === "new" ? "Novo financiamento" : "Editar financiamento"} onClose={() => setEditing(null)} wide>
        {editing !== null && <LoanForm loan={editing === "new" ? undefined : editing} onDone={() => setEditing(null)} />}
      </Sheet>
      <Sheet open={other !== null} title={other === "new" ? "Nova dívida" : "Editar dívida"} onClose={() => setOther(null)}>
        {other !== null && <OtherDebtForm debt={other === "new" ? undefined : other} onDone={() => setOther(null)} />}
      </Sheet>
    </>
  );
}
