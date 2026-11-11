import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { errorMessage } from "../api/client";
import { habitsApi } from "../api/habits";
import { money } from "../lib/format";
import { Alert, LoadingRegion, Skeleton } from "./ui";

/**
 * Modo sem culpa (v1.3): um plano curto, em passos, sem julgamento e sem recomendar produto
 * financeiro. Abre pelo aviso "Plano para equilibrar o mês" do Orçamento (MonthNotices).
 */
export function RecoveryPlan({ month }: { month: string }) {
  const plan = useQuery({ queryKey: ["budget", "recovery", month], queryFn: () => habitsApi.recovery(month) });
  const [spread, setSpread] = useState(3);
  if (plan.isPending) {
    return (
      <LoadingRegion label="Montando o plano">
        <Skeleton height={180} />
      </LoadingRegion>
    );
  }
  if (plan.isError) return <Alert tone="error">{errorMessage(plan.error)}</Alert>;
  const data = plan.data;
  if (Number(data.deficit) <= 0) return <p>O mês está equilibrado: receitas cobrem as despesas.</p>;
  const chosen = data.spread.find((s) => s.months === spread) ?? data.spread[0]!;
  const cuts = data.cuts.filter((c) => Number(c.above_average) > 0 || Number(c.total) > 0);

  return (
    <ol className="recovery-steps">
      <li>
        <h3>O tamanho da diferença</h3>
        <p>
          As despesas passaram as receitas em <strong>{money(data.deficit)}</strong>. É um número para planejar, não para se culpar: um mês
          mais pesado acontece com todo mundo.
        </p>
      </li>
      <li>
        <h3>Em quanto tempo cobrir</h3>
        <div className="segmented segmented--3" role="radiogroup" aria-label="Prazo para cobrir">
          {data.spread.map((s) => (
            <label key={s.months}>
              <input type="radio" name="spread" checked={spread === s.months} onChange={() => setSpread(s.months)} />
              {s.months === 1 ? "No próximo mês" : `Em ${s.months} meses`}
            </label>
          ))}
        </div>
        <p>
          Para cobrir {chosen.months === 1 ? "no próximo mês" : `em ${chosen.months} meses`}, separe <strong>{money(chosen.per_month)}</strong> por
          mês, com ajustes nos gastos ou alguma receita extra. Prazos mais longos pesam menos no dia a dia.
        </p>
      </li>
      {cuts.length > 0 && (
        <li>
          <h3>Onde ajustar</h3>
          <p className="muted small">Categorias não essenciais deste mês, comparadas com a média dos 3 meses anteriores.</p>
          <ul className="recovery-list">
            {cuts.map((c) => (
              <li key={c.category_id ?? "none"}>
                <span>{c.name}</span>
                <span className="small">
                  {money(c.total)}
                  {Number(c.average) > 0 && <span className="muted"> · média {money(c.average)}</span>}
                  {Number(c.above_average) > 0 && <strong> · {money(c.above_average)} acima</strong>}
                </span>
              </li>
            ))}
          </ul>
        </li>
      )}
      {data.fixed.length > 0 && (
        <li>
          <h3>Contas fixas para rever</h3>
          <p className="muted small">Assinaturas e serviços não essenciais. Pausar um deles por alguns meses já ajuda.</p>
          <ul className="recovery-list">
            {data.fixed.map((f) => (
              <li key={f.description}>
                <span>{f.description}</span>
                <span className="small">{money(f.monthly)} por mês</span>
              </li>
            ))}
          </ul>
        </li>
      )}
      <li>
        <h3>Próximo passo</h3>
        <p>
          Escolha um ajuste para começar nesta semana. Um desafio em Metas (por exemplo, “30 dias sem delivery”) ajuda a manter o
          combinado, e o Orçamento mostra o progresso todo dia.
        </p>
      </li>
    </ol>
  );
}
