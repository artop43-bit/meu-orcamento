import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CheckCheck, ListChecks } from "lucide-react";
import { Link } from "react-router";

import { useBudgetMutation, useCategories } from "../api/budget";
import { errorMessage } from "../api/client";
import { moneyApi, moneyKeys } from "../api/money";
import { CategorySelect } from "../components/budget";
import { EmptyGuide } from "../components/help";
import { Alert, Button, LoadingRegion, PageHeader, Skeleton } from "../components/ui";
import { announce } from "../lib/announce";
import { money, monthLabel, shortDate } from "../lib/format";

/** Despesas importadas do extrato aguardando conferência. */
export default function ReviewPage() {
  const queue = useQuery({ queryKey: moneyKeys.review, queryFn: moneyApi.review });
  const categories = useCategories();
  const [chosen, setChosen] = useState<Record<string, string>>({});
  const confirm = useBudgetMutation((ids: string[]) =>
    moneyApi.confirmReview(ids, Object.fromEntries(ids.map((id) => [id, chosen[id] ?? currentOf(id)]))),
  );
  const items = queue.data ?? [];
  const currentOf = (id: string) => items.find((e) => e.id === id)?.category_id ?? null;

  async function run(ids: string[]) {
    try {
      const result = await confirm.mutateAsync(ids);
      announce(`${result.count} despesa(s) conferida(s)`);
    } catch (err) {
      announce(errorMessage(err));
    }
  }

  return (
    <>
      <PageHeader
        title="Para revisar"
        subtitle="Despesas importadas do extrato. Confira a categoria e confirme."
        actions={
          items.length > 0 && (
            <Button type="button" loading={confirm.isPending} onClick={() => void run(items.map((e) => e.id))}>
              <CheckCheck size={16} /> Confirmar todas ({items.length})
            </Button>
          )
        }
      />
      {queue.isPending && (
        <LoadingRegion label="Carregando">
          <Skeleton height={200} />
        </LoadingRegion>
      )}
      {queue.isError && <Alert tone="error">{errorMessage(queue.error)}</Alert>}
      {queue.data && items.length === 0 && (
        <section className="card">
          <EmptyGuide
            icon={<ListChecks size={22} />}
            title="Nada pendente"
            text="Despesas importadas de extratos aparecem aqui para conferência antes de entrar nas análises."
            action={
              <Link className="btn btn--secondary" to="/ajustes/dados">
                Importar extrato
              </Link>
            }
          />
        </section>
      )}
      {items.length > 0 && (
        <section className="card">
          <div className="table-wrap" tabIndex={0} role="region" aria-label="Despesas para revisar">
            <table className="table review-table">
              <thead>
                <tr>
                  <th scope="col">Data</th>
                  <th scope="col">Descrição</th>
                  <th scope="col">Categoria</th>
                  <th scope="col" className="num">
                    Valor
                  </th>
                  <th scope="col">
                    <span className="sr-only">Ação</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {items.map((e) => (
                  <tr key={e.id}>
                    <td>{e.due_date ? shortDate(e.due_date) : monthLabel(e.month, true)}</td>
                    <td className="wrap">{e.description}</td>
                    <td>
                      <CategorySelect
                        label={`Categoria de ${e.description}`}
                        categories={categories.data ?? []}
                        value={chosen[e.id] ?? e.category_id ?? ""}
                        onChange={(v) => setChosen((c) => ({ ...c, [e.id]: v }))}
                      />
                    </td>
                    <td className="num">{money(e.amount)}</td>
                    <td>
                      <Button type="button" variant="secondary" onClick={() => void run([e.id])}>
                        Confirmar
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  );
}
