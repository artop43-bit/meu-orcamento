import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";

import { budgetApi, keys } from "../api/budget";
import { errorMessage } from "../api/client";
import { Alert, PageHeader } from "../components/ui";
import { money, monthLabel, percent } from "../lib/format";

export default function History() {
  const history = useQuery({ queryKey: [...keys.history, 12], queryFn: () => budgetApi.history(12) });

  const points = history.data ?? [];
  const max = Math.max(1, ...points.flatMap((p) => [Number(p.income), Number(p.expenses)]));
  const withData = points.filter((p) => p.has_data);
  const avgBalance = withData.length
    ? withData.reduce((sum, p) => sum + Number(p.balance), 0) / withData.length
    : null;

  return (
    <div className="stack">
      <PageHeader title="Histórico" subtitle="Renda, contas e saldo dos últimos 12 meses." />
      {history.isPending && <p className="muted">Carregando…</p>}
      {history.isError && <Alert tone="error">{errorMessage(history.error)}</Alert>}

      {history.data && (
        <>
          <section className="card stack">
            <div className="section-header">
              <h2>Últimos 12 meses</h2>
              <div className="legend">
                <span><i className="swatch swatch--income" /> Renda</span>
                <span><i className="swatch swatch--expense" /> Contas</span>
              </div>
            </div>
            <div className="chart" role="img" aria-label="Gráfico de renda e contas por mês">
              {points.map((p) => (
                <Link key={p.month} to={`/orcamento/${p.month}`} className="chart__col" title={monthLabel(p.month)}>
                  <div className="chart__bars">
                    <div className="chart__bar chart__bar--income" style={{ height: `${(Number(p.income) / max) * 100}%` }} />
                    <div className="chart__bar chart__bar--expense" style={{ height: `${(Number(p.expenses) / max) * 100}%` }} />
                  </div>
                  <span className="chart__label">{monthLabel(p.month, true)}</span>
                </Link>
              ))}
            </div>
            {avgBalance !== null && (
              <p className="muted small">
                Saldo médio nos meses com lançamentos: <strong>{money(avgBalance)}</strong>
              </p>
            )}
          </section>

          <section className="card">
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Mês</th>
                    <th className="num">Renda</th>
                    <th className="num">Contas</th>
                    <th className="num">Saldo</th>
                    <th className="num">Comprometido</th>
                  </tr>
                </thead>
                <tbody>
                  {[...points].reverse().map((p) => (
                    <tr key={p.month} className={p.has_data ? undefined : "muted"}>
                      <td>
                        <Link to={`/orcamento/${p.month}`}>{monthLabel(p.month)}</Link>
                      </td>
                      <td className="num">{money(p.income)}</td>
                      <td className="num">{money(p.expenses)}</td>
                      <td className={`num ${Number(p.balance) < 0 ? "tone--error" : ""}`}>{money(p.balance)}</td>
                      <td className="num">{percent(p.committed_pct)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
