import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router";

import { budgetApi, keys } from "../api/budget";
import { errorMessage } from "../api/client";
import { Chart } from "../components/chart/Chart";
import { Alert, PageHeader } from "../components/ui";
import { money, monthLabel, percent } from "../lib/format";

export default function History() {
  const history = useQuery({ queryKey: [...keys.history, 12], queryFn: () => budgetApi.history(12) });

  const points = history.data ?? [];
  const navigate = useNavigate();
  const withData = points.filter((p) => p.has_data);
  const avgBalance = withData.length
    ? withData.reduce((sum, p) => sum + Number(p.balance), 0) / withData.length
    : null;

  return (
    <div className="stack">
      <PageHeader title="Histórico" subtitle="Receitas, despesas e saldo dos últimos 12 meses." />
      {history.isPending && <p className="muted">Carregando…</p>}
      {history.isError && <Alert tone="error">{errorMessage(history.error)}</Alert>}

      {history.data && (
        <>
          <section className="card stack">
            <h2>Últimos 12 meses</h2>
            <Chart
              type="bar"
              labels={points.map((p) => ({ key: p.month, label: p.month }))}
              series={[
                { key: "income", name: "Receitas", color: "var(--accent)", values: points.map((p) => Number(p.income)) },
                { key: "expenses", name: "Despesas", color: "var(--expense)", values: points.map((p) => Number(p.expenses)) },
              ]}
              monthLabels
              description="Receitas e despesas por mês nos últimos 12 meses"
              onSelect={(key) => navigate(`/orcamento/${key}`)}
            />
            {avgBalance !== null && (
              <p className="muted small">
                Saldo médio nos meses com lançamentos: <strong>{money(avgBalance)}</strong>
              </p>
            )}
          </section>

          <section className="card">
            <div className="table-wrap" tabIndex={0} role="region" aria-label="Histórico mês a mês">
              <table className="table">
                <thead>
                  <tr>
                    <th>Mês</th>
                    <th className="num">Receitas</th>
                    <th className="num">Despesas</th>
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
