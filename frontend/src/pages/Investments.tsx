import { useEffect, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Landmark, Plus, ShieldCheck, Trash2, TrendingUp } from "lucide-react";
import { Link, useSearchParams } from "react-router";

import {
  analysisApi,
  INVESTMENT_KINDS,
  type Investment,
  type InvestmentKind,
} from "../api/analysis";
import { useBudgetMutation } from "../api/budget";
import { errorMessage } from "../api/client";
import { AllocationTarget } from "../components/AllocationTarget";
import { marketApi } from "../api/market";
import { Badge, Bar, FormActions, MoneyInput, requireMoney } from "../components/budget";
import { EmptyGuide, Tip } from "../components/help";
import { MarketSection, PortfolioComments } from "../components/market";
import { Alert, Button, Kpi, PageHeader, Sheet } from "../components/ui";
import { useUndo } from "../components/undo";
import { money, moneyInput, parseMoney, percent } from "../lib/format";

const KEY = ["budget", "investments"] as const;
// Tipos que costumam ter código na bolsa (ou cripto): o valor atual vem da cotação.
const QUOTED: InvestmentKind[] = ["acoes", "fiis", "cripto", "fundos"];
const KIND_COLORS: Record<InvestmentKind, string> = {
  // v1.6: cores do tema (versão própria no claro e no escuro, contraste testado).
  poupanca: "var(--chart-8)",
  renda_fixa: "var(--chart-2)",
  tesouro: "var(--accent)",
  fundos: "var(--chart-5)",
  acoes: "var(--chart-1)",
  fiis: "var(--chart-7)",
  cripto: "var(--chart-3)",
  previdencia: "var(--chart-4)",
  outro: "var(--subtle)",
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
  const [ticker, setTicker] = useState(investment?.ticker ?? "");
  const [quantity, setQuantity] = useState(investment?.quantity ? String(Number(investment.quantity)).replace(".", ",") : "");
  const [error, setError] = useState("");
  const quoted = QUOTED.includes(kind);

  const save = useBudgetMutation(async () => {
    const investedValue = parseMoney(invested);
    if (investedValue === null) throw new Error("Informe o valor investido.");
    // Valor atual em branco = igual ao investido.
    const currentValue = current.trim() ? requireMoney(current) : investedValue;
    const qty = quantity.trim() ? Number(quantity.replace(/\./g, "").replace(",", ".")) : null;
    if (qty !== null && !(qty > 0)) throw new Error("Quantidade inválida.");
    const data = {
      ticker: quoted && ticker.trim() ? ticker.trim().toUpperCase() : null,
      quantity: quoted && qty ? String(qty) : null,
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
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Ex.: CDB 110% CDI, Petrobras" required maxLength={80} autoFocus />
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
          <input value={institution} onChange={(e) => setInstitution(e.target.value)} placeholder="Ex.: Nubank, XP, Inter" maxLength={80} />
        </label>
        {quoted && (
          <>
            <label>
              <span className="field-label">
                Código (opcional){" "}
                <Tip>
                  Código na B3 (PETR4, MXRF11, BOVA11) ou do criptoativo (BTC, ETH). Com código e quantidade, o valor atual é atualizado pela
                  cotação.
                </Tip>
              </span>
              <input value={ticker} onChange={(e) => setTicker(e.target.value)} placeholder="Ex.: PETR4" maxLength={12} autoCapitalize="characters" />
            </label>
            <label>
              Quantidade
              <input inputMode="decimal" value={quantity} onChange={(e) => setQuantity(e.target.value)} placeholder="Ex.: 100 ou 0,005 (BTC)" />
            </label>
          </>
        )}
        <label>
          Quanto investiu
          <MoneyInput value={invested} onChange={setInvested} placeholder="Ex.: 5.000,00" />
        </label>
        <label>
          Valor atual
          <input
            inputMode="decimal"
            placeholder={quoted && ticker ? "Vem da cotação" : "Igual ao investido"}
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
          />
        </label>
      </div>
      <label className="check">
        <input type="checkbox" checked={reserve} onChange={(e) => setReserve(e.target.checked)} />
        Compõe a reserva de emergência
      </label>
      <FormActions loading={save.isPending} onCancel={onDone} label={investment ? "Salvar" : "Adicionar"} />
    </form>
  );
}

function InvestmentRow({ investment }: { investment: Investment }) {
  const [editing, setEditing] = useState(false);
  const undo = useUndo();
  const ret = Number(investment.return_amount);

  return (
    <li className="item">
      <Sheet open={editing} title="Editar investimento" onClose={() => setEditing(false)}>
        <InvestmentForm investment={investment} onDone={() => setEditing(false)} />
      </Sheet>
      <button type="button" className="item__main" onClick={() => setEditing(true)} title="Editar">
        <span className="item__title">
          <span className="dot" style={{ background: KIND_COLORS[investment.kind] }} aria-hidden />
          {investment.name}
        </span>
        <span className="item__meta">
          {INVESTMENT_KINDS[investment.kind]}
          {investment.ticker && ` · ${investment.ticker}`}
          {investment.ticker && investment.quantity && ` × ${Number(investment.quantity).toLocaleString("pt-BR")}`}
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
        onClick={() =>
          undo.remove({
            ids: [investment.id],
            message: `"${investment.name}" excluído`,
            commit: () => analysisApi.deleteInvestment(investment.id),
          })
        }
      >
        <Trash2 size={17} />
      </button>
    </li>
  );
}

/** Atualiza pela cotação os investimentos com código e quantidade (a cada 2 min com a tela aberta). */
function usePortfolioRefresh(enabled: boolean) {
  const queryClient = useQueryClient();
  const refresh = useQuery({
    queryKey: ["market", "portfolio"],
    queryFn: marketApi.refreshPortfolio,
    enabled,
    staleTime: 60_000,
    refetchInterval: 120_000,
  });
  const updated = refresh.data?.updated.length ?? 0;
  useEffect(() => {
    if (refresh.dataUpdatedAt && updated > 0) void queryClient.invalidateQueries({ queryKey: KEY });
  }, [refresh.dataUpdatedAt, updated, queryClient]);
  return refresh;
}

export default function Investments() {
  const [params] = useSearchParams();
  const tab = ["cotacoes", "mercado"].includes(params.get("secao") ?? "") ? "cotacoes" : "carteira";
  return (
    <>
      <PageHeader
        title="Investimentos"
        subtitle={tab === "cotacoes" ? "Índices, moedas, ações, criptoativos e renda fixa." : "Posição consolidada da carteira e rentabilidade."}
      />
      <nav className="page-tabs no-print" aria-label="Seções de investimentos" style={{ marginBottom: 20 }}>
        <Link to="/investimentos" aria-current={tab === "carteira" ? "page" : undefined}>
          Minha carteira
        </Link>
        <Link to="/investimentos?secao=cotacoes" aria-current={tab === "cotacoes" ? "page" : undefined}>
          Cotações
        </Link>
      </nav>
      {tab === "cotacoes" ? <MarketSection /> : <Portfolio />}
    </>
  );
}

function Portfolio() {
  const list = useQuery({ queryKey: KEY, queryFn: analysisApi.investments });
  const [adding, setAdding] = useState(false);
  const items = list.data ?? [];
  const undo = useUndo();

  const invested = items.reduce((s, i) => s + Number(i.invested_amount), 0);
  const current = items.reduce((s, i) => s + Number(i.current_value), 0);
  const reserve = items.filter((i) => i.is_emergency_reserve).reduce((s, i) => s + Number(i.current_value), 0);
  const byKind = Object.entries(
    items.reduce<Record<string, number>>((acc, i) => {
      acc[i.kind] = (acc[i.kind] ?? 0) + Number(i.current_value);
      return acc;
    }, {}),
  ).sort((a, b) => b[1] - a[1]);

  const gain = current - invested;
  const refresh = usePortfolioRefresh(items.length > 0);

  return (
    <>
      <div className="row" style={{ justifyContent: "flex-end", marginBottom: 16 }}>
        <Button type="button" onClick={() => setAdding(true)}>
          <Plus size={16} /> Novo investimento
        </Button>
      </div>
      {list.isError && <Alert tone="error">{errorMessage(list.error)}</Alert>}

      <div className="stack" style={{ gap: 20 }}>
        {items.length > 0 && (
          <div className="kpis kpis--3">
            <Kpi icon={<Landmark size={17} />} label="Patrimônio" value={money(current)} foot={`Investido ${money(invested)}`} />
            <Kpi
              icon={<TrendingUp size={17} />}
              tone={gain < 0 ? "expense" : "accent"}
              label="Rendimento"
              value={money(gain)}
              valueClass={gain < 0 ? "tone--error" : "tone--ok"}
              foot={invested > 0 ? percent(Math.round((gain / invested) * 1000) / 10) + " sobre o investido" : undefined}
            />
            <Kpi icon={<ShieldCheck size={17} />} tone="neutral" label="Reserva de emergência" value={money(reserve)} foot="Conta no score financeiro" />
          </div>
        )}

        <div className="layout-main-side">
          <section className="card stack">
            <h2>Carteira</h2>
            {list.isPending && <p className="muted">Carregando…</p>}
            {items.length === 0 && !list.isPending && (
              <EmptyGuide
                icon={<Landmark size={22} />}
                title="Sua carteira está vazia"
                text="Cadastre os investimentos e marque os que compõem a reserva de emergência (considerada no score financeiro)."
                example={<>Ex.: “Reserva no CDB” R$ 5.000 (reserva) · “Petrobras” PETR4 × 100 (valor pela cotação)</>}
                action={
                  <Button type="button" onClick={() => setAdding(true)}>
                    <Plus size={16} /> Adicionar investimento
                  </Button>
                }
              />
            )}
            <ul className="items">
              {items
                .filter((i) => !undo.isHidden(i.id))
                .map((i) => (
                <InvestmentRow key={i.id} investment={i} />
              ))}
            </ul>
            <p className="muted small" style={{ margin: 0 }}>
              Ativos com código e quantidade são atualizados pela cotação. Para os demais, atualize o valor periodicamente com o saldo
              da instituição.
            </p>
          </section>

          <div className="stack" style={{ gap: 20 }}>
            {byKind.length > 0 && (
              <section className="card stack">
                <h2>Alocação</h2>
                <ul className="breakdown">
                  {byKind.map(([kind, value]) => (
                    <li key={kind}>
                      <div className="split">
                        <span>
                          <span className="dot" style={{ background: KIND_COLORS[kind as InvestmentKind] }} aria-hidden />
                          {INVESTMENT_KINDS[kind as InvestmentKind]}
                        </span>
                        <span className="num">
                          {money(value)}{" "}
                          <span className="muted small">{percent(Math.round((value / current) * 1000) / 10)}</span>
                        </span>
                      </div>
                      <Bar pct={current > 0 ? (value / current) * 100 : 0} color={KIND_COLORS[kind as InvestmentKind]} />
                    </li>
                  ))}
                </ul>
                <AllocationTarget current={Object.fromEntries(byKind)} labels={INVESTMENT_KINDS as Record<string, string>} />
              </section>
            )}
            {refresh.data && <PortfolioComments comments={refresh.data.comments} />}
            <Indicators />
          </div>
        </div>
      </div>

      <Sheet open={adding} title="Novo investimento" onClose={() => setAdding(false)}>
        <InvestmentForm onDone={() => setAdding(false)} />
      </Sheet>
    </>
  );
}
