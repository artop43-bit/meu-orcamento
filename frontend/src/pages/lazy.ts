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
  HubPreferences: () => import("./HubPreferences"),
  HubSettings: () => import("./HubSettings"),
  Messaging: () => import("./Messaging"),
  CrmDashboards: () => import("./crm/Dashboards"),
  CrmPipeline: () => import("./crm/Pipeline"),
  CrmContacts: () => import("./crm/Contacts"),
  CrmSources: () => import("./crm/DataSources"),
  CatalogShell: () => import("./commerce/CatalogShell"),
  CatalogPage: () => import("./commerce/CatalogPage"),
  ProposalsShell: () => import("./commerce/ProposalsShell"),
  ProposalsPage: () => import("./commerce/ProposalsPage"),
  ProjectsShell: () => import("./work/ProjectsShell"),
  ProjectsPage: () => import("./work/ProjectsPage"),
  AgendaShell: () => import("./work/AgendaShell"),
  AgendaPage: () => import("./work/AgendaPage"),
  VaultShell: () => import("./memory/VaultShell"),
  VaultPage: () => import("./memory/VaultPage"),
  NotebookShell: () => import("./memory/NotebookShell"),
  NotebookPage: () => import("./memory/NotebookPage"),
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
/** Tela sob demanda que também pode ser baixada antes de abrir (`preload`). */
export type PageComponent = AnyComponent & { preload: () => Promise<void> };
const warmers: (() => Promise<unknown>)[] = [];

function page(load: () => Promise<{ default: AnyComponent }>): PageComponent {
  let ready: AnyComponent | null = null;
  const fetch = () =>
    load().then((module) => {
      ready = module.default;
      return module;
    });
  const Lazy = lazy(fetch);
  warmers.push(fetch);
  const Page = function Page(props: object) {
    return createElement(ready ?? Lazy, props);
  } as PageComponent;
  Page.preload = () => fetch().then(() => undefined);
  return Page;
}

export const Analysis = page(loaders.Analysis);
export const CalendarPage = page(loaders.Calendar);
export const CardsPage = page(loaders.Cards);
export const HubPreferencesPage = page(loaders.HubPreferences);
export const HubSettingsPage = page(loaders.HubSettings);
export const MessagingPage = page(loaders.Messaging);
export const CrmDashboardsPage = page(loaders.CrmDashboards);
export const CrmPipelinePage = page(loaders.CrmPipeline);
export const CrmContactsPage = page(loaders.CrmContacts);
export const CrmSourcesPage = page(loaders.CrmSources);
export const CatalogShell = page(loaders.CatalogShell);
export const CatalogPage = page(loaders.CatalogPage);
export const ProposalsShell = page(loaders.ProposalsShell);
export const ProposalsPage = page(loaders.ProposalsPage);
export const ProjectsShell = page(loaders.ProjectsShell);
export const ProjectsPage = page(loaders.ProjectsPage);
export const AgendaShell = page(loaders.AgendaShell);
export const AgendaPage = page(loaders.AgendaPage);
export const VaultShell = page(loaders.VaultShell);
export const VaultPage = page(loaders.VaultPage);
export const NotebookShell = page(loaders.NotebookShell);
export const NotebookPage = page(loaders.NotebookPage);
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

/**
 * Primeira tela de cada solução, baixada no clique do cartão do Hub enquanto a animação de
 * entrada toca. A tela do mês (/orcamento) já vem no pacote principal (App.tsx).
 */
const SOLUTION_ENTRY_PAGES: [prefix: string, page: PageComponent][] = [
  ["/mensageria", MessagingPage],
  ["/crm", CrmDashboardsPage],
  ["/catalogo", CatalogPage],
  ["/propostas", ProposalsPage],
  ["/projetos", ProjectsPage],
  ["/agenda", AgendaPage],
  ["/cofre", VaultPage],
  ["/caderno", NotebookPage],
];

/** Baixa o código da tela inicial da solução; nunca falha (a tela tenta de novo ao abrir). */
export function preloadSolutionRoute(to: string): Promise<void> {
  const entry = SOLUTION_ENTRY_PAGES.find(([prefix]) => to === prefix || to.startsWith(`${prefix}/`));
  if (!entry) return Promise.resolve();
  return entry[1].preload().catch(() => undefined);
}

let preloaded = false;

export function preloadPages() {
  if (preloaded) return;
  preloaded = true;
  const run = () => warmers.forEach((warm) => void warm().catch(() => undefined));
  // Logo depois de entrar (v1.4.3): no celular o aparelho quase nunca fica "ocioso" a tempo e
  // a primeira visita a cada tela esperava o código ser baixado.
  if ("requestIdleCallback" in window) window.requestIdleCallback(run, { timeout: 600 });
  else setTimeout(run, 300);
}
