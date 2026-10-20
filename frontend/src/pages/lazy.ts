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
  Support: () => import("./Support"),
  Inbox: () => import("./Inbox"),
  Debts: () => import("./Debts"),
  Splits: () => import("./Splits"),
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

export const Analysis = lazy(loaders.Analysis);
export const CalendarPage = lazy(loaders.Calendar);
export const CardsPage = lazy(loaders.Cards);
export const PreferencesPage = lazy(loaders.Preferences);
export const SupportPage = lazy(loaders.Support);
export const InboxPage = lazy(loaders.Inbox);
export const DebtsPage = lazy(loaders.Debts);
export const SplitsPage = lazy(loaders.Splits);
export const LoanTablePage = lazy(loaders.LoanTable);
export const ProfilePage = lazy(loaders.Profile);
export const AdminPage = lazy(loaders.Admin);
export const AccountsPage = lazy(loaders.Accounts);
export const ReviewPage = lazy(loaders.Review);
export const SearchPage = lazy(loaders.Search);
export const SettingsHub = lazy(loaders.Settings);
export const SettingsLayout = lazy(() => loaders.Settings().then((m) => ({ default: m.SettingsLayout })));
export const ShortcutsPage = lazy(() => loaders.Settings().then((m) => ({ default: m.ShortcutsPage })));
export const HelpPage = lazy(loaders.Help);
export const Categories = lazy(loaders.Categories);
export const DataPage = lazy(loaders.Data);
export const Goals = lazy(loaders.Goals);
export const History = lazy(loaders.History);
export const Investments = lazy(loaders.Investments);
export const RecurringPage = lazy(loaders.Recurring);
export const Report = lazy(loaders.Report);
export const AnnualReport = lazy(loaders.AnnualReport);
export const ReleaseNotesPage = lazy(loaders.ReleaseNotes);
export const OnboardingPage = lazy(loaders.Onboarding);  // configuração inicial guiada (janela)
export const Unsubscribe = lazy(() => loaders.PublicActions().then((m) => ({ default: m.Unsubscribe })));
export const NotMe = lazy(() => loaders.PublicActions().then((m) => ({ default: m.NotMe })));
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
