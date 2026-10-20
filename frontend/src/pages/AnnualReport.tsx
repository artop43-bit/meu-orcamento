import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";

import { useMe } from "../api/auth";
import { errorMessage } from "../api/client";
import { dataApi } from "../api/data";
import { Alert, Button } from "../components/ui";
import { money, monthLabel, percent } from "../lib/format";

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
        <Button type="button" onClick={() => window.print()}>
          Imprimir / salvar em PDF
        </Button>
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

      <p className="muted small">
        Documento informativo gerado pelo Meu Orçamento a partir dos lançamentos registrados. Não substitui informes de rendimentos nem
        documentos fiscais.
      </p>
    </article>
  );
}
