import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";

import { useMe } from "../api/auth";
import { errorMessage } from "../api/client";
import { dataApi, type TaxReport } from "../api/data";
import { PdfButton } from "../components/PdfButton";
import { Alert, Button } from "../components/ui";
import { money, monthLabel, percent } from "../lib/format";

/** v1.4: o ano na ordem das fichas da declaração do Imposto de Renda. */
function TaxSection({ tax }: { tax: TaxReport }) {
  const empty = !tax.deductions.length && !tax.incomes.length && !tax.assets.length && !tax.debts.length;
  if (empty) return null;
  return (
    <section className="report__section report__tax" id="imposto-de-renda">
      <h2>Para o Imposto de Renda</h2>
      <p className="muted small">
        Apoio para preencher a declaração. Confira com os informes de rendimentos do banco e da empresa e com os recibos.
      </p>
      {tax.deductions.length > 0 && (
        <>
          <h3>Pagamentos dedutíveis · {money(tax.deductions_total)}</h3>
          {tax.deductions.map((d) => (
            <div key={d.kind} className="report__tax-group">
              <p className="report__tax-title">
                {d.label}: <strong>{money(d.total)}</strong>
              </p>
              <table>
                <tbody>
                  {d.items.map((item, i) => (
                    <tr key={i}>
                      <td>{new Date(`${item.date}T12:00:00`).toLocaleDateString("pt-BR")}</td>
                      <td>{item.description}</td>
                      <td className="num">{money(item.amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </>
      )}
      {tax.incomes.length > 0 && (
        <>
          <h3>Rendimentos</h3>
          <ul className="report__list">
            {tax.incomes.map((i) => (
              <li key={i.kind}>
                {i.label}: {money(i.total)}
              </li>
            ))}
          </ul>
        </>
      )}
      {tax.assets.length > 0 && (
        <>
          <h3>Bens e direitos em 31/12</h3>
          <ul className="report__list">
            {tax.assets.map((a, i) => (
              <li key={i}>
                {a.description}: {money(a.value)}
              </li>
            ))}
          </ul>
          <p className="muted small">Investimentos pelo valor aplicado (custo), como pede a declaração.</p>
        </>
      )}
      {tax.debts.length > 0 && (
        <>
          <h3>Dívidas e ônus em 31/12</h3>
          <ul className="report__list">
            {tax.debts.map((d, i) => (
              <li key={i}>
                {d.description}: {money(d.value)}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

/** Resumo anual pensado para impressão ("Salvar como PDF" no navegador). */
export default function AnnualReport() {
  const params = useParams();
  const current = new Date().getFullYear();
  const year = params.ano && /^\d{4}$/.test(params.ano) ? Number(params.ano) : current;
  const { data: user } = useMe();
  const data = useQuery({ queryKey: ["budget", "annual", year], queryFn: () => dataApi.annual(year) });

  if (data.isPending) return <p className="muted">Carregando…</p>;
  if (data.isError) return <Alert tone="error">{errorMessage(data.error)}</Alert>;
  const d = data.data;
  const withData = d.months.filter((m) => Number(m.income) > 0 || Number(m.expenses) > 0);

  return (
    <article className="report stack">
      <div className="row no-print">
        <Link className="btn btn--secondary" to="/ajustes/dados?aba=exportar">
          Voltar
        </Link>
        <Button type="button" variant="secondary" onClick={() => window.print()}>
          Imprimir
        </Button>
        <PdfButton path={`/export/annual.pdf?year=${year}`} name={`resumo-anual-${year}.pdf`} />
      </div>

      <header className="report__header">
        <div>
          <p className="brand">Meu Orçamento</p>
          <h1>Resumo anual de {year}</h1>
        </div>
        <p className="muted small">
          {user?.email}
          <br />
          Gerado em {new Date().toLocaleDateString("pt-BR")}
          {year === current && (
            <>
              <br />
              Ano em andamento: valores até hoje
            </>
          )}
        </p>
      </header>

      <section className="report__section">
        <div className="stats">
          <div className="stat">
            <span className="stat__label">Receitas</span>
            <strong className="stat__value">{money(d.income)}</strong>
          </div>
          <div className="stat">
            <span className="stat__label">Despesas</span>
            <strong className="stat__value">{money(d.expenses)}</strong>
          </div>
          <div className="stat">
            <span className="stat__label">Resultado</span>
            <strong className="stat__value">{money(d.balance)}</strong>
          </div>
          <div className="stat">
            <span className="stat__label">Taxa de poupança</span>
            <strong className="stat__value">{percent(d.savings_rate)}</strong>
          </div>
          <div className="stat">
            <span className="stat__label">Investimentos (hoje)</span>
            <strong className="stat__value">{money(d.investments_total)}</strong>
          </div>
        </div>
      </section>

      <section className="report__section">
        <h2>Mês a mês</h2>
        {withData.length === 0 ? (
          <p className="muted">Sem lançamentos neste ano.</p>
        ) : (
          <table className="table table--compact">
            <thead>
              <tr>
                <th>Mês</th>
                <th className="num">Receitas</th>
                <th className="num">Despesas</th>
                <th className="num">Resultado</th>
                <th className="num">Comprometido</th>
              </tr>
            </thead>
            <tbody>
              {withData.map((m) => (
                <tr key={m.month}>
                  <td>{monthLabel(m.month.slice(0, 7))}</td>
                  <td className="num">{money(m.income)}</td>
                  <td className="num">{money(m.expenses)}</td>
                  <td className="num">{money(m.balance)}</td>
                  <td className="num">{percent(m.committed_pct)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {d.by_category.length > 0 && (
        <section className="report__section">
          <h2>Despesas por categoria</h2>
          <table className="table table--compact">
            <thead>
              <tr>
                <th>Categoria</th>
                <th className="num">Total</th>
                <th className="num">% das despesas</th>
              </tr>
            </thead>
            <tbody>
              {d.by_category.map((c) => (
                <tr key={c.name}>
                  <td>{c.name}</td>
                  <td className="num">{money(c.total)}</td>
                  <td className="num">{percent(Math.round(c.share * 1000) / 10)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {d.goals.length > 0 && (
        <section className="report__section">
          <h2>Metas</h2>
          <ul className="report__list">
            {d.goals.map((g) => (
              <li key={g.name}>
                {g.name}: {money(g.current_amount)} de {money(g.target_amount)}
                {g.completed ? " (concluída)" : ""}
              </li>
            ))}
          </ul>
        </section>
      )}

      {d.tax && <TaxSection tax={d.tax} />}

      <p className="muted small">
        Documento informativo gerado pelo Meu Orçamento a partir dos lançamentos registrados. Não substitui informes de rendimentos nem
        documentos fiscais.
      </p>
    </article>
  );
}
