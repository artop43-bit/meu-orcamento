import type { QueryClient, QueryKey } from "@tanstack/react-query";

import { analysisApi } from "../api/analysis";
import { budgetApi, keys } from "../api/budget";
import { DEBTS_KEY, debtsApi } from "../api/debts";
import { extrasApi, extrasKeys } from "../api/extras";
import { moneyApi, moneyKeys } from "../api/money";
import { SPLITS_KEY, sharingApi } from "../api/sharing";
import { thisMonth } from "./format";

/**
 * Dados principais de cada tela do menu, pedidos antes do clique (ao passar o mouse, focar
 * ou encostar o dedo no item). Assim a tela já abre preenchida, sem o "esqueleto" piscando.
 * As chaves são as mesmas que cada tela usa; se a tela mudar a dela, só perde o adiantamento.
 */
type Query = { queryKey: QueryKey; queryFn: () => Promise<unknown> };

const ROUTES: Record<string, () => Query[]> = {
  "/orcamento": () => [{ queryKey: keys.month(thisMonth()), queryFn: () => budgetApi.month(thisMonth()) }],
  "/contas": () => [{ queryKey: moneyKeys.accounts, queryFn: moneyApi.accounts }],
  "/cartoes": () => [{ queryKey: extrasKeys.cards, queryFn: extrasApi.cards }],
  "/dividas": () => [{ queryKey: DEBTS_KEY, queryFn: debtsApi.overview }],
  "/divisoes": () => [{ queryKey: SPLITS_KEY, queryFn: sharingApi.board }],
  "/calendario": () => [{ queryKey: keys.calendar(thisMonth()), queryFn: () => budgetApi.calendar(thisMonth()) }],
  "/metas": () => [{ queryKey: keys.goals, queryFn: budgetApi.goals }],
  "/investimentos": () => [{ queryKey: ["budget", "investments"], queryFn: analysisApi.investments }],
  "/analises": () => [
    { queryKey: ["budget", "analysis", "overview", thisMonth()], queryFn: () => analysisApi.overview(thisMonth()) },
  ],
  "/historico": () => [{ queryKey: [...keys.history, 12], queryFn: () => budgetApi.history(12) }],
};

export function prefetchRoute(queryClient: QueryClient, to: string) {
  for (const query of ROUTES[to]?.() ?? []) {
    // Dados com menos de 30 s não são pedidos de novo (mesmo tempo do app).
    void queryClient.prefetchQuery({ ...query, staleTime: 30_000 });
  }
}

/** Props para um link do menu: adianta os dados da tela ao apontar, focar ou tocar. */
export function prefetchProps(queryClient: QueryClient, to: string) {
  const run = () => prefetchRoute(queryClient, to);
  return { onMouseEnter: run, onFocus: run, onTouchStart: run };
}
