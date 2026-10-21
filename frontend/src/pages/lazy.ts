import { createElement, lazy, type ComponentType } from "react";

/**
 * Telas carregadas sob demanda: o primeiro carregamento do app fica leve. Logo depois de
 * entrar, preloadPages() baixa o resto em segundo plano, então trocar de aba continua instantâneo.
 *
 * `page()` em vez de `lazy()` puro: depois que a tela foi baixada, ela é desenhada na hora.
 * Com `lazy()` sozinho, a primeira abertura de cada tela ainda "suspende" por um instante
 * (mesmo já baixada) e o cartão vazio de carregamento pisca antes do conteúdo.
 */
const loaders = {
  Analysis: () => import("./Analysis"),
  Calendar: () => import("./Calendar"),
  Cards: () => import("./Cards"),
  Preferences: () => import("./Preferences"),
  Support: () => import("./Support"),
  Inbox: () => import("./Inbox"),
  Debts: () => import("./Debts"),
  Splits: () => import("./Splits"),
  AppInstall: () => import("./AppInstall"),
  LoanTable: () => import("./LoanTable"),
  Profile: () => import("./Profile"),
  Admin: () => import("./Admin"),
  Accounts: () => import("./Accounts"),
  Review: () => import("./Review"),
  Search: () => import("./Search"),
  Settings: () => import("./Settings"),
  Help: () => import("./Help"),
  Categories: () => import("./Categories"),
  Data: () => import("./Data"),
  Goals: () => import("./Goals"),
  History: () => import("./History"),
  Investments: () => import("./Investments"),
  Recurring: () => import("./Recurring"),
  Report: () => import("./Report"),
  AnnualReport: () => import("./AnnualReport"),
  ReleaseNotes: () => import("./ReleaseNotes"),
  Onboarding: () => import("./Onboarding"),
  PublicActions: () => import("./PublicActions"),
  Security: () => import("./Security"),
  Legal: () => import("./Legal"),
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyComponent = ComponentType<any>;
const warmers: (() => Promise<unknown>)[] = [];

function page(load: () => Promise<{ default: AnyComponent }>): AnyComponent {
  let ready: AnyComponent | null = null;
  const fetch = () =>
    load().then((module) => {
      ready = module.default;
      return module;
    });
  const Lazy = lazy(fetch);
  warmers.push(fetch);
  return function Page(props: object) {
    return createElement(ready ?? Lazy, props);
  };
}

export const Analysis = page(loaders.Analysis);
export const CalendarPage = page(loaders.Calendar);
export const CardsPage = page(loaders.Cards);
export const PreferencesPage = page(loaders.Preferences);
export const SupportPage = page(loaders.Support);
export const InboxPage = page(loaders.Inbox);
export const DebtsPage = page(loaders.Debts);
export const SplitsPage = page(loaders.Splits);
export const AppInstallPage = page(loaders.AppInstall);
export const LoanTablePage = page(loaders.LoanTable);
export const ProfilePage = page(loaders.Profile);
export const AdminPage = page(loaders.Admin);
export const AccountsPage = page(loaders.Accounts);
export const ReviewPage = page(loaders.Review);
export const SearchPage = page(loaders.Search);
export const SettingsHub = page(loaders.Settings);
export const SettingsLayout = page(() => loaders.Settings().then((m) => ({ default: m.SettingsLayout })));
export const HelpPage = page(loaders.Help);
export const Categories = page(loaders.Categories);
export const DataPage = page(loaders.Data);
export const Goals = page(loaders.Goals);
export const History = page(loaders.History);
export const Investments = page(loaders.Investments);
export const RecurringPage = page(loaders.Recurring);
export const Report = page(loaders.Report);
export const AnnualReport = page(loaders.AnnualReport);
export const ReleaseNotesPage = page(loaders.ReleaseNotes);
export const OnboardingPage = page(loaders.Onboarding);  // configuração inicial guiada (janela)
export const Unsubscribe = page(() => loaders.PublicActions().then((m) => ({ default: m.Unsubscribe })));
export const NotMe = page(() => loaders.PublicActions().then((m) => ({ default: m.NotMe })));
export const Security = page(loaders.Security);
export const Privacy = page(() => loaders.Legal().then((m) => ({ default: m.Privacy })));
export const Terms = page(() => loaders.Legal().then((m) => ({ default: m.Terms })));

let preloaded = false;

export function preloadPages() {
  if (preloaded) return;
  preloaded = true;
  const run = () => warmers.forEach((warm) => void warm().catch(() => undefined));
  if ("requestIdleCallback" in window) window.requestIdleCallback(run, { timeout: 3000 });
  else setTimeout(run, 1200);
}
