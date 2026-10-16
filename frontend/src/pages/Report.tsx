import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";

import { analysisApi } from "../api/analysis";
import { useMe } from "../api/auth";
import { useCategories, useMonth } from "../api/budget";
import { errorMessage } from "../api/client";
import { Alert, Button } from "../components/ui";
import { money, monthLabel, percent, shortDate, thisMonth } from "../lib/format";

/** Relatório mensal pensado para impressão ("Salvar como PDF" no navegador). */
export default function Report() {
  const params = useParams();
  const month = params.month && /^\d{4}-\d{2}$/.test(params.month) ? params.month : thisMonth();
  const data = useMonth(month);
  const categories = useCategories();
  const { data: user } = useMe();
  const overview = useQuery({
    queryKey: ["budget", "analysis", "overview", month],
    queryFn: () => analysisApi.overview(month),
  });
  const names = new Map((categories.data ?? []).map((c) => [c.id, c.name]));

  if (data.isPending) return <p className="muted">Carregando…</p>;
  if (data.isError) return <Alert tone="error">{errorMessage(data.error)}</Alert>;

  const s = data.data.summary;
  const score = overview.data?.score;

  return (
    <article className="report stack">
      <div className="row no-print">
        <Link className="btn btn--secondary" to="/dados">
          Voltar
        </Link>
        <Button type="button" onClick={() => window.print()}>
          Imprimir / salvar em PDF
        </Button>
      </div>

      <header className="report__header">
        <div>
          <p className="brand">Meu Orçamento</p>
          <h1>Relatório de {monthLabel(month).toLowerCase()}</h1>
        </div>
        <p className="muted small">
          {user?.email}
          <br />
          Gerado em {new Date().toLocaleDateString("pt-BR")}
        </p>
      </header>

      <section className="report__section">
        <div className="stats">
          <div className="stat">
            <span className="stat__label">Renda</span>
            <strong className="stat__value">{money(s.income_total)}</strong>
          </div>
          <div className="stat">
            <span className="stat__label">Contas</span>
            <strong className="stat__value">{money(s.expense_total)}</strong>
          </div>
          <div className="stat">
            <span className="stat__label">Saldo</span>
            <strong className="stat__value">{money(s.balance)}</strong>
          </div>
          <div className="stat">
            <span className="stat__label">Comprometido</span>
            <strong className="stat__value">{percent(s.committed_pct)}</strong>
          </div>
          {score?.score !== undefined && score?.score !== null && (
            <div className="stat">
              <span className="stat__label">Score financeiro</span>
              <strong className="stat__value">
                {score.score} <span className="small muted">{score.label}</span>
              </strong>
            </div>
          )}
        </div>
      </section>

      <section className="report__section">
        <h2>Renda</h2>
        <table className="table">
          <tbody>
            {data.data.incomes.map((i) => (
              <tr key={i.id}>
                <td>{i.description}</td>
                <td className="num">{money(i.amount)}</td>
              </tr>
            ))}
            {data.data.incomes.length === 0 && (
              <tr>
                <td className="muted">Nenhuma renda lançada.</td>
              </tr>
            )}
          </tbody>
        </table>
      </section>

      <section className="report__section">
        <h2>Contas</h2>
        <table className="table">
          <thead>
            <tr>
              <th>Descrição</th>
              <th>Categoria</th>
              <th>Vencimento</th>
              <th>Situação</th>
              <th className="num">Valor</th>
            </tr>
          </thead>
          <tbody>
            {data.data.expenses.map((e) => (
              <tr key={e.id}>
                <td className="wrap">
                  {e.description}
                  {e.installment_total && ` (${e.installment_number}/${e.installment_total})`}
                </td>
                <td>{e.category_id ? names.get(e.category_id) : "Sem categoria"}</td>
                <td>{shortDate(e.due_date)}</td>
                <td>{e.paid ? "Paga" : "A pagar"}</td>
                <td className="num">{money(e.amount)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td colSpan={3}>
                Pago {money(s.paid_total)} · A pagar {money(s.pending_total)}
              </td>
              <td />
              <td className="num">
                <strong>{money(s.expense_total)}</strong>
              </td>
            </tr>
          </tfoot>
        </table>
      </section>

      {s.by_category.length > 0 && (
        <section className="report__section">
          <h2>Por categoria</h2>
          <table className="table">
            <tbody>
              {s.by_category.map((c) => (
                <tr key={c.category_id ?? "none"}>
                  <td>
                    {c.name} <span className="muted small">{c.is_essential ? "· essencial" : ""}</span>
                  </td>
                  <td className="num">{money(c.total)}</td>
                  <td className="num muted">
                    {percent(Math.round((Number(c.total) / Number(s.expense_total)) * 1000) / 10)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </article>
  );
}
