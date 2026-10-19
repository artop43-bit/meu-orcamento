import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff, Info, Plus, RefreshCw, Search, TrendingDown, TrendingUp, X } from "lucide-react";

import { errorMessage } from "../api/client";
import {
  DISCLAIMER,
  marketApi,
  marketKeys,
  useAsset,
  useMarketOverview,
  useWatchlist,
  type AssetRange,
  type Quote,
  type Simulation,
} from "../api/market";
import { announce } from "../lib/announce";
import { money, parseMoney } from "../lib/format";
import { Chart } from "./chart/Chart";
import { Tip } from "./help";
import { Alert, Button, LoadingRegion, Sheet, Skeleton } from "./ui";

const KIND_LABEL: Record<Quote["kind"], string> = {
  index: "Índice",
  stock: "Ação",
  fii: "Fundo imobiliário",
  crypto: "Cripto",
  currency: "Moeda",
  unknown: "Ativo",
};

function price(q: Quote): string {
  if (q.price === null) return "—";
  if (q.kind === "index") return q.price.toLocaleString("pt-BR", { maximumFractionDigits: 0 }) + " pts";
  return money(q.price);
}

function Change({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined) return <span className="muted small">—</span>;
  const up = value > 0;
  const down = value < 0;
  const text = `${up ? "+" : ""}${value.toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%`;
  return (
    <span className={`change small ${up ? "tone--ok" : down ? "tone--error" : "muted"}`}>
      {up ? <TrendingUp size={13} aria-hidden /> : down ? <TrendingDown size={13} aria-hidden /> : null}
      <span className="sr-only">{up ? "alta de " : down ? "queda de " : "variação "}</span>
      {text}
    </span>
  );
}

/** Aviso fixo exigido: o app informa, não recomenda (CVM, Resolução 20). */
export function Disclaimer() {
  return (
    <p className="disclaimer" role="note">
      <Info size={15} aria-hidden /> {DISCLAIMER} Cotações podem ter atraso.
    </p>
  );
}

function QuoteCard({ q, onOpen }: { q: Quote; onOpen?: (s: string) => void }) {
  const body = (
    <>
      <span className="quote__name">{q.name}</span>
      <strong className="quote__price">{price(q)}</strong>
      <Change value={q.change_pct} />
    </>
  );
  return onOpen ? (
    <button type="button" className="quote" onClick={() => onOpen(q.symbol)}>
      {body}
      <span className="sr-only">(abrir ficha)</span>
    </button>
  ) : (
    <div className="quote">{body}</div>
  );
}

function Ranking({ title, items, onOpen }: { title: string; items: Quote[]; onOpen: (s: string) => void }) {
  return (
    <section className="card stack stack--tight">
      <h3 style={{ margin: 0 }}>{title}</h3>
      {items.length === 0 ? (
        <p className="muted small" style={{ margin: 0 }}>
          Indisponível no momento (pregão fechado ou fonte inacessível).
        </p>
      ) : (
        <ol className="rank">
          {items.map((q) => (
            <li key={q.symbol}>
              <button type="button" onClick={() => onOpen(q.symbol)}>
                <span className="rank__symbol">{q.symbol}</span>
                <span className="rank__name muted small">{q.name}</span>
                <span className="num">{price(q)}</span>
                <Change value={q.change_pct} />
              </button>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

// ---------------------------------------------------------------- ficha do ativo

const RANGES: { value: AssetRange; label: string }[] = [
  { value: "5d", label: "5 dias" },
  { value: "1mo", label: "1 mês" },
  { value: "3mo", label: "3 meses" },
  { value: "1y", label: "1 ano" },
];

function AssetSheet({ symbol, onClose, watching }: { symbol: string | null; onClose: () => void; watching: Set<string> }) {
  const [range, setRange] = useState<AssetRange>("1mo");
  const asset = useAsset(symbol, range);
  const toggle = useWatchToggle();
  const q = asset.data?.quote;
  const history = asset.data?.history.filter((p) => p.close !== null) ?? [];
  const isWatching = symbol ? watching.has(symbol) : false;

  return (
    <Sheet open={!!symbol} title={symbol ? `Ficha · ${symbol}` : ""} onClose={onClose} wide>
      {asset.isPending && (
        <LoadingRegion label="Carregando a ficha">
          <Skeleton height={240} />
        </LoadingRegion>
      )}
      {asset.isError && <Alert tone="error">{errorMessage(asset.error)}</Alert>}
      {q && (
        <div className="stack">
          <div className="split">
            <div>
              <p className="muted small" style={{ margin: 0 }}>
                {KIND_LABEL[q.kind]} · {q.symbol}
              </p>
              <h3 style={{ margin: "2px 0" }}>{q.name}</h3>
            </div>
            <div style={{ textAlign: "right" }}>
              <strong className="quote__price">{price(q)}</strong>
              <div>
                <Change value={q.change_pct} />
              </div>
            </div>
          </div>
          <div className="segmented" role="group" aria-label="Período do gráfico">
            {RANGES.map((r) => (
              <button key={r.value} type="button" aria-pressed={range === r.value} onClick={() => setRange(r.value)}>
                {r.label}
              </button>
            ))}
          </div>
          {history.length > 1 ? (
            <Chart
              type="area"
              labels={history.map((p) => ({ key: p.date, label: `${p.date.slice(8)}/${p.date.slice(5, 7)}` }))}
              series={[{ key: "close", name: "Fechamento", color: "#4e79a7", values: history.map((p) => p.close) }]}
              description={`Preço de ${q.name} em ${RANGES.find((r) => r.value === range)?.label}`}
              height={220}
            />
          ) : (
            <p className="muted">Sem histórico para o período.</p>
          )}
          <dl className="facts">
            {q.day_low != null && q.day_high != null && (
              <div>
                <dt>Mínima e máxima do dia</dt>
                <dd>
                  {money(q.day_low)} – {money(q.day_high)}
                </dd>
              </div>
            )}
            {q.year_low != null && q.year_high != null && (
              <div>
                <dt>Mínima e máxima em 52 semanas</dt>
                <dd>
                  {money(q.year_low)} – {money(q.year_high)}
                </dd>
              </div>
            )}
            {q.volume != null && (
              <div>
                <dt>Volume negociado</dt>
                <dd>{q.volume.toLocaleString("pt-BR")}</dd>
              </div>
            )}
          </dl>
          <Button
            type="button"
            variant="secondary"
            loading={toggle.isPending}
            onClick={() => symbol && toggle.mutate({ symbol, watch: !isWatching })}
          >
            {isWatching ? <EyeOff size={16} /> : <Eye size={16} />} {isWatching ? "Remover da lista" : "Acompanhar"}
          </Button>
          <Disclaimer />
        </div>
      )}
    </Sheet>
  );
}

function useWatchToggle() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ symbol, watch }: { symbol: string; watch: boolean }): Promise<void> => {
      if (watch) await marketApi.watch(symbol);
      else await marketApi.unwatch(symbol);
    },
    onSuccess: (_, { symbol, watch }) => {
      announce(watch ? `Acompanhando ${symbol}` : `${symbol} removido da lista`);
      return queryClient.invalidateQueries({ queryKey: marketKeys.watchlist });
    },
  });
}

// ---------------------------------------------------------------- acompanhando

function Watchlist({ onOpen }: { onOpen: (s: string) => void }) {
  const list = useWatchlist();
  const toggle = useWatchToggle();
  const [symbol, setSymbol] = useState("");
  const [error, setError] = useState("");

  async function add(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      await toggle.mutateAsync({ symbol: symbol.trim().toUpperCase(), watch: true });
      setSymbol("");
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <section className="card stack">
      <div className="section-header">
        <h2>
          Lista de acompanhamento{" "}
          <Tip>Ativos selecionados para acompanhamento: códigos da B3 (PETR4, MXRF11) ou criptoativos (BTC, ETH, SOL).</Tip>
        </h2>
      </div>
      <form className="row" onSubmit={add}>
        <label className="list-tools__search" style={{ flex: 1 }}>
          <Search size={16} aria-hidden />
          <span className="sr-only">Código do ativo</span>
          <input value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="Ex.: PETR4, MXRF11, BTC" maxLength={12} required />
        </label>
        <Button type="submit" variant="secondary" loading={toggle.isPending}>
          <Plus size={16} /> Adicionar
        </Button>
      </form>
      <Alert tone="error">{error}</Alert>
      {list.data && list.data.length === 0 && (
        <p className="muted small" style={{ margin: 0 }}>
          Nenhum ativo na lista. Informe um código ou abra um ativo abaixo e selecione “Acompanhar”.
        </p>
      )}
      {list.data && list.data.length > 0 && (
        <ul className="quotes">
          {list.data.map((q) => (
            <li key={q.symbol} className="quotes__item">
              <QuoteCard q={q} onOpen={onOpen} />
              <button
                type="button"
                className="icon-btn"
                aria-label={`Parar de acompanhar ${q.symbol}`}
                onClick={() => toggle.mutate({ symbol: q.symbol, watch: false })}
              >
                <X size={15} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// ---------------------------------------------------------------- renda fixa

function Simulator() {
  const [amount, setAmount] = useState("1.000,00");
  const [months, setMonths] = useState("12");
  const [cdb, setCdb] = useState("100");
  const [result, setResult] = useState<Simulation | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function run(event: FormEvent) {
    event.preventDefault();
    setError("");
    const value = Number(parseMoney(amount) ?? 0);
    if (value <= 0) return setError("Informe um valor maior que zero.");
    setLoading(true);
    try {
      setResult(await marketApi.simulate(value, Number(months) || 12, Number(cdb) || 100));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  const best = result ? Math.max(...result.results.map((r) => r.net)) : 0;
  return (
    <section className="card stack">
      <h2>
        Simulador de renda fixa{" "}
        <Tip>
          Projeção de cada aplicação com as taxas atuais (Selic, CDI e IPCA do Banco Central), já descontado o IR quando aplicável.
          Estimativa sujeita à variação das taxas.
        </Tip>
      </h2>
      <form className="grid-3" onSubmit={run}>
        <label>
          Valor aplicado
          <input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="Ex.: 1.000,00" />
        </label>
        <label>
          Prazo (meses)
          <input type="number" inputMode="numeric" min={1} max={600} value={months} onChange={(e) => setMonths(e.target.value)} />
        </label>
        <label>
          <span className="field-label">
            Rentabilidade do CDB (% do CDI) <Tip>Percentual do CDI oferecido pelo emissor, ex.: 100% ou 110%.</Tip>
          </span>
          <input type="number" inputMode="numeric" min={50} max={200} value={cdb} onChange={(e) => setCdb(e.target.value)} />
        </label>
        <div className="form-actions" style={{ gridColumn: "1 / -1" }}>
          <Button type="submit" loading={loading}>
            Simular
          </Button>
        </div>
      </form>
      <Alert tone="error">{error}</Alert>
      {result && (
        <div className="table-wrap" tabIndex={0} role="region" aria-label="Resultado da simulação">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Aplicação</th>
                <th scope="col">Taxa ao ano</th>
                <th scope="col">IR</th>
                <th scope="col">Valor final líquido</th>
                <th scope="col">Ganho acima da inflação</th>
              </tr>
            </thead>
            <tbody>
              {result.results.map((r) => (
                <tr key={r.key}>
                  <th scope="row">{r.name}</th>
                  <td className="num">{r.annual_rate.toLocaleString("pt-BR")}%</td>
                  <td className="num">{r.ir_pct ? `${r.ir_pct.toLocaleString("pt-BR")}%` : "isento"}</td>
                  <td className="num">
                    <strong className={r.net === best ? "tone--ok" : undefined}>{money(r.net)}</strong>
                  </td>
                  <td className={`num ${r.real_gain !== null && r.real_gain < 0 ? "tone--error" : ""}`}>
                    {r.real_gain === null ? "—" : money(r.real_gain)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted small" style={{ margin: "8px 0 0" }}>
            Selic {result.selic}% · CDI {result.cdi}% · IPCA 12 meses {result.ipca_12m ?? "—"}%. Poupança sem TR; Tesouro com taxa de
            custódia de 0,2%. Não considera IOF (resgates antes de 30 dias).
          </p>
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------- seção Mercado

export function MarketSection() {
  const overview = useMarketOverview();
  const watch = useWatchlist();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState<string | null>(null);
  const data = overview.data;
  const watching = new Set((watch.data ?? []).map((q) => q.symbol));
  const updated = data ? new Date(data.fetched_at).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }) : null;

  return (
    <div className="stack" style={{ gap: 20 }}>
      <Disclaimer />
      <div className="split small muted">
        <span>{updated ? `Atualizado às ${updated} · atualiza sozinho a cada 2 minutos` : "Carregando cotações…"}</span>
        <button
          type="button"
          className="link-btn"
          onClick={() => void queryClient.invalidateQueries({ queryKey: ["market"] })}
          aria-label="Atualizar cotações agora"
        >
          <RefreshCw size={14} aria-hidden /> Atualizar
        </button>
      </div>
      {overview.isPending && (
        <LoadingRegion label="Carregando as cotações">
          <Skeleton height={120} />
        </LoadingRegion>
      )}
      {overview.isError && <Alert tone="error">{errorMessage(overview.error)}</Alert>}
      {data && (
        <>
          <section className="card stack">
            <h2>Visão geral</h2>
            <ul className="quotes">
              {data.indexes.map((q) => (
                <li key={q.symbol}>
                  <QuoteCard q={q} />
                </li>
              ))}
              {[...data.currencies, ...data.crypto].map((q) => (
                <li key={q.symbol}>
                  <QuoteCard q={q} onOpen={q.kind === "crypto" ? setOpen : undefined} />
                </li>
              ))}
            </ul>
            {data.indexes_need_token && (
              <p className="muted small" style={{ margin: 0 }}>
                Ibovespa e IFIX ficam disponíveis após a configuração da chave da brapi.dev no servidor.
              </p>
            )}
          </section>

          <Watchlist onOpen={setOpen} />

          <div className="grid-3 grid-3--cards">
            <Ranking title="Maiores altas do dia" items={data.gainers} onOpen={setOpen} />
            <Ranking title="Maiores baixas do dia" items={data.losers} onOpen={setOpen} />
            <Ranking title="Mais negociadas" items={data.most_traded} onOpen={setOpen} />
          </div>
          <p className="muted small" style={{ margin: 0 }}>
            Ações com volume relevante na B3. A presença na lista não constitui recomendação de compra ou venda.
          </p>

          <section className="card stack">
            <h2>Renda fixa hoje</h2>
            <div className="stats">
              {(
                [
                  ["Selic", data.fixed_income.selic, "meta ao ano"],
                  ["CDI", data.fixed_income.cdi, "ao ano"],
                  ["IPCA", data.fixed_income.ipca_12m, "últimos 12 meses"],
                ] as const
              ).map(([label, value, suffix]) => (
                <div className="stat" key={label}>
                  <span className="stat__label">{label}</span>
                  <strong className="stat__value">
                    {value ? `${value.value.toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%` : "—"}
                  </strong>
                  <span className="muted small">{suffix}</span>
                </div>
              ))}
            </div>
            <p className="muted small" style={{ margin: 0 }}>
              Fonte: Banco Central do Brasil.
            </p>
          </section>
        </>
      )}
      <Simulator />
      <AssetSheet symbol={open} onClose={() => setOpen(null)} watching={watching} />
    </div>
  );
}

export function PortfolioComments({ comments }: { comments: { tone: string; title: string; text: string }[] }) {
  if (comments.length === 0) return null;
  return (
    <section className="card stack">
      <h2>Análise da carteira</h2>
      <ul className="insights">
        {comments.map((c) => (
          <li key={c.title} className={`insight insight--${c.tone === "warning" ? "warning" : c.tone === "good" ? "praise" : "info"}`}>
            <span>
              <strong className="insight__title">{c.title}</strong>
              <span className="insight__text">{c.text}</span>
            </span>
          </li>
        ))}
      </ul>
      <Disclaimer />
    </section>
  );
}

