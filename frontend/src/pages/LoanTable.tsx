import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";

import { useMe } from "../api/auth";
import { errorMessage } from "../api/client";
import { DEBTS_KEY, debtsApi, type Installment, type Loan } from "../api/debts";
import { Alert, Button } from "../components/ui";
import { money, shortDate } from "../lib/format";

const rate = (v: number) => `${v.toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%`;

/** Planilha (CSV com ";" e vírgula decimal, abre direto no Excel em português). */
function downloadCsv(loan: Loan, rows: Installment[]) {
  const num = (v: string) => Number(v).toFixed(2).replace(".", ",");
  const lines = [
    ["Parcela", "Vencimento", "Valor da parcela", "Juros", "Amortização", "Seguro e taxas", "Saldo devedor"].join(";"),
    ...rows.map((r) => [r.number, shortDate(r.due), num(r.payment), num(r.interest), num(r.amortization), num(r.extras), num(r.balance)].join(";")),
  ];
  const blob = new Blob(["﻿" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `tabela-${loan.name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

/** Tabela de amortização completa, pensada para imprimir ou salvar em PDF. */
export default function LoanTable() {
  const { id = "" } = useParams();
  const { data: user } = useMe();
  const overview = useQuery({ queryKey: DEBTS_KEY, queryFn: debtsApi.overview });
  const table = useQuery({ queryKey: [...DEBTS_KEY, "table", id], queryFn: () => debtsApi.table(id) });
  const loan = overview.data?.loans.find((l) => l.id === id);

  if (table.isError) return <Alert tone="error">{errorMessage(table.error)}</Alert>;
  if (!table.data || !loan) return <p className="muted">Carregando…</p>;
  const rows = table.data;

  return (
    <article className="report stack">
      <div className="row no-print">
        <Link className="btn btn--secondary" to="/dividas">
          Voltar
        </Link>
        <Button type="button" variant="secondary" onClick={() => downloadCsv(loan, rows)}>
          Baixar planilha
        </Button>
        <Button type="button" onClick={() => window.print()}>
          Imprimir / salvar em PDF
        </Button>
      </div>
      <header className="report__header">
        <div>
          <p className="brand">Meu Orçamento</p>
          <h1>{loan.name}</h1>
          <p className="muted small" style={{ margin: 0 }}>
            {loan.kind_label}
            {loan.institution && ` · ${loan.institution}`} · Sistema {loan.system === "price" ? "Price" : "SAC"}
          </p>
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
            <span className="stat__label">Valor financiado</span>
            <strong className="stat__value">{money(loan.principal)}</strong>
          </div>
          <div className="stat">
            <span className="stat__label">Taxa</span>
            <strong className="stat__value">
              {rate(loan.monthly_rate)} a.m. · {rate(loan.yearly_rate)} a.a.
            </strong>
          </div>
          <div className="stat">
            <span className="stat__label">CET</span>
            <strong className="stat__value">{rate(loan.cet_yearly)} a.a.</strong>
          </div>
          <div className="stat">
            <span className="stat__label">Total de juros</span>
            <strong className="stat__value">{money(loan.total_interest)}</strong>
          </div>
          <div className="stat">
            <span className="stat__label">Total pago no contrato</span>
            <strong className="stat__value">{money(loan.total_paid)}</strong>
          </div>
          <div className="stat">
            <span className="stat__label">Saldo devedor hoje</span>
            <strong className="stat__value">{money(loan.balance)}</strong>
          </div>
        </div>
      </section>
      <section className="report__section">
        <div className="table-wrap" tabIndex={0} role="region" aria-label="Tabela de parcelas">
          <table className="table loan-table">
            <thead>
              <tr>
                <th scope="col">Parcela</th>
                <th scope="col">Vencimento</th>
                <th scope="col" className="num">
                  Parcela
                </th>
                <th scope="col" className="num">
                  Juros
                </th>
                <th scope="col" className="num">
                  Amortização
                </th>
                <th scope="col" className="num">
                  Seguro e taxas
                </th>
                <th scope="col" className="num">
                  Saldo devedor
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.number} className={r.number <= loan.paid_installments ? "is-paid" : undefined}>
                  <td>
                    {r.number}/{loan.installments}
                    {r.number <= loan.paid_installments && <span className="sr-only"> (paga)</span>}
                  </td>
                  <td>{shortDate(r.due)}</td>
                  <td className="num">{money(r.payment)}</td>
                  <td className="num">{money(r.interest)}</td>
                  <td className="num">{money(r.amortization)}</td>
                  <td className="num">{money(r.extras)}</td>
                  <td className="num">{money(r.balance)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted small">Linhas em destaque: parcelas já pagas. Valores calculados pelo app a partir dos dados do contrato.</p>
      </section>
    </article>
  );
}
