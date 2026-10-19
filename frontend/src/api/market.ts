import { useQuery } from "@tanstack/react-query";

import type { Indicators } from "./analysis";
import { api } from "./client";

export type Quote = {
  symbol: string;
  name: string;
  kind: "index" | "stock" | "fii" | "crypto" | "currency" | "unknown";
  price: number | null;
  change_pct: number | null;
  day_high?: number | null;
  day_low?: number | null;
  volume?: number | null;
  year_high?: number | null;
  year_low?: number | null;
  currency?: string;
  logo?: string | null;
  updated_at?: string | null;
};

export type MarketOverview = {
  indexes: Quote[];
  indexes_need_token: boolean;
  currencies: Quote[];
  crypto: Quote[];
  gainers: Quote[];
  losers: Quote[];
  most_traded: Quote[];
  fixed_income: Indicators;
  disclaimer: string;
  fetched_at: string;
};

export type AssetRange = "5d" | "1mo" | "3mo" | "1y";

export type AssetSheet = {
  quote: Quote;
  history: { date: string; close: number | null }[];
  range: AssetRange;
  disclaimer: string;
};

export type Simulation = {
  amount: number;
  months: number;
  selic: number;
  cdi: number;
  ipca_12m: number | null;
  results: {
    key: string;
    name: string;
    annual_rate: number;
    ir_pct: number;
    gross: number;
    net: number;
    earnings_net: number;
    real_gain: number | null;
  }[];
  disclaimer: string;
};

export type PortfolioRefresh = {
  updated: { id: string; ticker: string; price: number; change_pct: number | null; current_value: string }[];
  comments: { tone: "info" | "warning" | "good"; title: string; text: string }[];
  disclaimer: string;
};

export const DISCLAIMER = "Informativo, não é recomendação de investimento.";

export const marketApi = {
  overview: () => api.get<MarketOverview>("/market/overview"),
  asset: (symbol: string, range: AssetRange) =>
    api.get<AssetSheet>(`/market/asset/${encodeURIComponent(symbol)}?range=${range}`),
  watchlist: () => api.get<Quote[]>("/market/watchlist"),
  watch: (symbol: string) => api.post<{ symbol: string }>("/market/watchlist", { symbol }),
  unwatch: (symbol: string) => api.delete(`/market/watchlist/${encodeURIComponent(symbol)}`),
  simulate: (amount: number, months: number, cdbPct: number) =>
    api.get<Simulation>(`/market/fixed-income/simulate?amount=${amount}&months=${months}&cdb_pct=${cdbPct}`),
  refreshPortfolio: () => api.post<PortfolioRefresh>("/market/portfolio/refresh"),
};

// O servidor guarda as cotações em cache por ~2 min; a tela atualiza sozinha nesse ritmo.
const LIVE = { staleTime: 60_000, refetchInterval: 120_000, refetchIntervalInBackground: false };

export const marketKeys = {
  overview: ["market", "overview"] as const,
  watchlist: ["market", "watchlist"] as const,
  asset: (symbol: string, range: AssetRange) => ["market", "asset", symbol, range] as const,
};

export function useMarketOverview(enabled = true) {
  return useQuery({ queryKey: marketKeys.overview, queryFn: marketApi.overview, enabled, ...LIVE });
}

export function useWatchlist(enabled = true) {
  return useQuery({ queryKey: marketKeys.watchlist, queryFn: marketApi.watchlist, enabled, ...LIVE });
}

export function useAsset(symbol: string | null, range: AssetRange) {
  return useQuery({
    queryKey: marketKeys.asset(symbol ?? "", range),
    queryFn: () => marketApi.asset(symbol!, range),
    enabled: !!symbol,
    staleTime: 5 * 60_000,
  });
}
