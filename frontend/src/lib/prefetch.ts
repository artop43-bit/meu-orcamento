import type { QueryClient, QueryKey } from "@tanstack/react-query";

import { analysisApi } from "../api/analysis";
import { budgetApi, keys } from "../api/budget";
import { crmApi, crmKeys } from "../api/crm";
import { catalogApi, catalogKeys, proposalsApi, proposalsKeys } from "../api/commerce";
import { agendaApi, agendaKeys, projectsApi, projectsKeys } from "../api/work";
import { AGENDA_ALL_LAYERS, shiftIsoDate, startOfWeekIso } from "./work";
import { DEBTS_KEY, debtsApi } from "../api/debts";
import { extrasApi, extrasKeys } from "../api/extras";
import { messagingApi, messagingKeys } from "../api/messaging";
import { moneyApi, moneyKeys } from "../api/money";
import { SPLITS_KEY, sharingApi } from "../api/sharing";
import { thisMonth, todayISO } from "./format";

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
  "/mensageria": () => [
    { queryKey: messagingKeys.session, queryFn: messagingApi.session },
    { queryKey: messagingKeys.chats("all", ""), queryFn: () => messagingApi.chats("all", "") },
  ],
  "/crm": () => [
    { queryKey: crmKeys.dashboards, queryFn: crmApi.dashboards },
    { queryKey: crmKeys.sources, queryFn: crmApi.sources },
  ],
  "/catalogo": () => [
    { queryKey: catalogKeys.items("all", ""), queryFn: () => catalogApi.items() },
    { queryKey: catalogKeys.orders, queryFn: catalogApi.orders },
  ],
  "/propostas": () => [{ queryKey: proposalsKeys.list("all"), queryFn: () => proposalsApi.list("all") }],
  "/projetos": () => [{ queryKey: projectsKeys.list("all"), queryFn: () => projectsApi.list("") }],
  "/agenda": () => {
    const start = startOfWeekIso(todayISO());
    const end = shiftIsoDate(start, 6);
    const layersKey = AGENDA_ALL_LAYERS.slice().sort().join(",");
    return [
      {
        queryKey: agendaKeys.timeline(start, end, layersKey),
        queryFn: () => agendaApi.timeline(start, end, AGENDA_ALL_LAYERS),
      },
    ];
  },
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
