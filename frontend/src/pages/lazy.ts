import { lazy } from "react";

/**
 * Telas carregadas sob demanda: o primeiro carregamento do app fica leve. Logo depois de
 * entrar, preloadPages() baixa o resto em segundo plano, então trocar de aba continua instantâneo.
 */
const loaders = {
  Analysis: () => import("./Analysis"),
  Calendar: () => import("./Calendar"),
  Cards: () => import("./Cards"),
  Preferences: () => import("./Preferences"),
  AdminFeedback: () => import("./AdminFeedback"),
  Help: () => import("./Help"),
  Categories: () => import("./Categories"),
  Data: () => import("./Data"),
  Goals: () => import("./Goals"),
  History: () => import("./History"),
  Investments: () => import("./Investments"),
  Recurring: () => import("./Recurring"),
  Report: () => import("./Report"),
  Security: () => import("./Security"),
  Legal: () => import("./Legal"),
};

export const Analysis = lazy(loaders.Analysis);
export const CalendarPage = lazy(loaders.Calendar);
export const CardsPage = lazy(loaders.Cards);
export const PreferencesPage = lazy(loaders.Preferences);
export const AdminFeedbackPage = lazy(loaders.AdminFeedback);
export const HelpPage = lazy(loaders.Help);
export const Categories = lazy(loaders.Categories);
export const DataPage = lazy(loaders.Data);
export const Goals = lazy(loaders.Goals);
export const History = lazy(loaders.History);
export const Investments = lazy(loaders.Investments);
export const RecurringPage = lazy(loaders.Recurring);
export const Report = lazy(loaders.Report);
export const Security = lazy(loaders.Security);
export const Privacy = lazy(() => loaders.Legal().then((m) => ({ default: m.Privacy })));
export const Terms = lazy(() => loaders.Legal().then((m) => ({ default: m.Terms })));

let preloaded = false;

export function preloadPages() {
  if (preloaded) return;
  preloaded = true;
  const run = () => Object.values(loaders).forEach((load) => void load().catch(() => undefined));
  if ("requestIdleCallback" in window) window.requestIdleCallback(run, { timeout: 3000 });
  else setTimeout(run, 1200);
}
