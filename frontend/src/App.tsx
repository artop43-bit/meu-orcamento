import { Suspense } from "react";
import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from "react-router";

import { useMe } from "./api/auth";
import { errorMessage } from "./api/client";
import { CrmShell } from "./components/CrmShell";
import { HubShell } from "./components/HubShell";
import { MessagingShell } from "./components/MessagingShell";
import { Shell } from "./components/Shell";
import { SolutionGate, SolutionTransitionProvider } from "./components/SolutionTransition";
import ForgotPassword from "./pages/ForgotPassword";
import Hub from "./pages/Hub";
import Login from "./pages/Login";
import MonthPage from "./pages/Month";
import Register from "./pages/Register";
import ResetPassword from "./pages/ResetPassword";
import VerifyEmail from "./pages/VerifyEmail";
import {
  AccountsPage,
  AnnualReport,
  AdminPage,
  Analysis,
  CalendarPage,
  CardsPage,
  Categories,
  CrmContactsPage,
  CrmDashboardsPage,
  CrmPipelinePage,
  CrmSourcesPage,
  DataPage,
  Goals,
  HelpPage,
  History,
  HubPreferencesPage,
  HubSettingsPage,
  Investments,
  MessagingPage,
  NotMe,
  PreferencesPage,
  ProfilePage,
  Privacy,
  RecurringPage,
  ReleaseNotesPage,
  Report,
  ReviewPage,
  SearchPage,
  SupportPage,
  InboxPage,
  DebtsPage,
  SplitsPage,
  AppInstallPage,
  CatalogPage,
  CatalogShell,
  LoanTablePage,
  ProjectsPage,
  ProjectsShell,
  ProposalsPage,
  ProposalsShell,
  AgendaPage,
  AgendaShell,
  VaultPage,
  VaultShell,
  NotebookPage,
  NotebookShell,
  Unsubscribe,
  Security,
  SettingsHub,
  SettingsLayout,
  Terms,
} from "./pages/lazy";

function FullPageMessage({ children }: { children: React.ReactNode }) {
  return (
    <main className="auth">
      <p className="muted">{children}</p>
    </main>
  );
}

/** Páginas que exigem login. */
function RequireAuth() {
  const me = useMe();
  const location = useLocation();
  if (me.isPending) return <FullPageMessage>Carregando…</FullPageMessage>;
  if (me.isError) return <FullPageMessage>{errorMessage(me.error)}</FullPageMessage>;
  if (!me.data) return <Navigate to="/entrar" replace state={{ from: location.pathname }} />;
  return <Outlet />;
}

/** Aviso enquanto o código de uma tela é baixado (fica por baixo da animação de entrada). */
const loadingPage = <FullPageMessage>Carregando…</FullPageMessage>;

/** Páginas só para visitantes (login, cadastro): quem já entrou vai para o início. */
function GuestOnly() {
  const me = useMe();
  if (me.isPending) return <FullPageMessage>Carregando…</FullPageMessage>;
  if (me.data) return <Navigate to="/" replace />;
  return <Outlet />;
}

export default function App() {
  return (
    <BrowserRouter>
      {/* A transição entre soluções fica fora do <Suspense>: continua na tela enquanto a solução carrega. */}
      <SolutionTransitionProvider>
        <Suspense fallback={loadingPage}>
          <Routes>
            <Route element={<GuestOnly />}>
              <Route path="/entrar" element={<Login />} />
              <Route path="/cadastro" element={<Register />} />
              <Route path="/esqueci-senha" element={<ForgotPassword />} />
            </Route>
            {/* Acessíveis com ou sem login (abertas a partir de links de e-mail). */}
            <Route path="/verificar-email" element={<VerifyEmail />} />
            <Route path="/redefinir-senha" element={<ResetPassword />} />
            <Route path="/privacidade" element={<Privacy />} />
            <Route path="/termos" element={<Terms />} />
            <Route path="/descadastrar" element={<Unsubscribe />} />
            <Route path="/nao-fui-eu" element={<NotMe />} />
            <Route element={<RequireAuth />}>
              {/* Hub de Soluções e áreas compartilhadas da conta/plataforma */}
              <Route element={<HubShell />}>
                <Route path="/" element={<Hub />} />
                <Route path="/hub" element={<Navigate to="/" replace />} />
                <Route path="/perfil" element={<ProfilePage />} />
                <Route path="/configuracoes" element={<HubSettingsPage />} />
                <Route path="/seguranca" element={<Security />} />
                <Route path="/preferencias" element={<HubPreferencesPage />} />
                <Route path="/app" element={<AppInstallPage />} />
                <Route path="/notas" element={<ReleaseNotesPage />} />
                <Route path="/mensagens" element={<InboxPage />} />
                <Route path="/mensagens/conversas" element={<InboxPage />} />
                <Route path="/mensagens/conversas/:id" element={<InboxPage />} />
                <Route path="/admin" element={<AdminPage />} />
                <Route path="/admin/sugestoes" element={<Navigate to="/admin?aba=solicitacoes" replace />} />
              </Route>

              {/* Redirecionamentos de endereços antigos da conta para o Hub */}
              <Route path="/ajustes/perfil" element={<Navigate to="/perfil" replace />} />
              <Route path="/ajustes/seguranca" element={<Navigate to="/seguranca" replace />} />
              <Route path="/ajustes/app" element={<Navigate to="/app" replace />} />
              <Route path="/ajustes/notas" element={<Navigate to="/notas" replace />} />
              <Route path="/ajustes/solicitacoes" element={<SupportPage />} />
              <Route path="/ajustes/solicitacoes/:id" element={<SupportPage />} />

              {/* Solução: Mensageria (SolutionGate barra o salto direto de outra solução).
                  A chave separa a moldura de cada solução: o React Router reaproveitaria a mesma. */}
              <Route
                element={
                  <SolutionGate key="mensageria" solution="mensageria" fallback={loadingPage}>
                    <MessagingShell />
                  </SolutionGate>
                }
              >
                <Route path="/mensageria" element={<MessagingPage />} />
                <Route path="/mensageria/:chatId" element={<MessagingPage />} />
              </Route>

              {/* Solução: Dashboard & CRM */}
              <Route
                element={
                  <SolutionGate key="dashboard-crm" solution="dashboard-crm" fallback={loadingPage}>
                    <CrmShell />
                  </SolutionGate>
                }
              >
                <Route path="/crm" element={<CrmDashboardsPage />} />
                <Route path="/crm/funil" element={<CrmPipelinePage />} />
                <Route path="/crm/contatos" element={<CrmContactsPage />} />
                <Route path="/crm/fontes" element={<CrmSourcesPage />} />
              </Route>

              {/* Solução: Catálogo & Estoque */}
              <Route
                element={
                  <SolutionGate key="catalogo" solution="catalogo" fallback={loadingPage}>
                    <CatalogShell />
                  </SolutionGate>
                }
              >
                <Route path="/catalogo" element={<CatalogPage tab="items" />} />
                <Route path="/catalogo/pedidos" element={<CatalogPage tab="orders" />} />
              </Route>

              {/* Solução: Propostas & PDFs */}
              <Route
                element={
                  <SolutionGate key="propostas" solution="propostas" fallback={loadingPage}>
                    <ProposalsShell />
                  </SolutionGate>
                }
              >
                <Route path="/propostas" element={<ProposalsPage />} />
              </Route>

              {/* Solução: Projetos & Tarefas */}
              <Route
                element={
                  <SolutionGate key="projetos" solution="projetos" fallback={loadingPage}>
                    <ProjectsShell />
                  </SolutionGate>
                }
              >
                <Route path="/projetos" element={<ProjectsPage />} />
              </Route>

              {/* Solução: Agenda & Compromissos */}
              <Route
                element={
                  <SolutionGate key="agenda" solution="agenda" fallback={loadingPage}>
                    <AgendaShell />
                  </SolutionGate>
                }
              >
                <Route path="/agenda" element={<AgendaPage />} />
              </Route>

              {/* Solução: Cofre & Garantias */}
              <Route
                element={
                  <SolutionGate key="cofre" solution="cofre" fallback={loadingPage}>
                    <VaultShell />
                  </SolutionGate>
                }
              >
                <Route path="/cofre" element={<VaultPage />} />
              </Route>

              {/* Solução: Caderno & Conhecimento */}
              <Route
                element={
                  <SolutionGate key="caderno" solution="caderno" fallback={loadingPage}>
                    <NotebookShell />
                  </SolutionGate>
                }
              >
                <Route path="/caderno" element={<NotebookPage />} />
              </Route>

              {/* Solução: Meu Orçamento */}
              <Route
                element={
                  <SolutionGate key="meu-orcamento" solution="meu-orcamento" fallback={loadingPage}>
                    <Shell />
                  </SolutionGate>
                }
              >
                <Route path="/orcamento/:month?" element={<MonthPage />} />
                <Route path="/calendario/:month?" element={<CalendarPage />} />
                <Route path="/cartoes" element={<CardsPage />} />
                <Route path="/contas" element={<AccountsPage />} />
                <Route path="/revisar" element={<ReviewPage />} />
                <Route path="/busca" element={<SearchPage />} />
                <Route path="/dividas" element={<DebtsPage />} />
                <Route path="/divisoes" element={<SplitsPage />} />
                <Route path="/dividas/:id/tabela" element={<LoanTablePage />} />
                <Route path="/metas" element={<Goals />} />
                <Route path="/historico" element={<History />} />
                <Route path="/analises" element={<Analysis />} />
                <Route path="/investimentos" element={<Investments />} />
                <Route path="/ajustes" element={<SettingsLayout />}>
                  <Route index element={<SettingsHub />} />
                  <Route path="recorrencias" element={<RecurringPage />} />
                  <Route path="categorias" element={<Categories />} />
                  <Route path="dados" element={<DataPage />} />
                  <Route path="preferencias" element={<PreferencesPage />} />
                  {/* Atalhos de teclado ficam em Preferências desde a v1.1. */}
                  <Route path="atalhos" element={<Navigate to="/ajustes/preferencias#atalhos" replace />} />
                  <Route path="ajuda" element={<HelpPage />} />
                </Route>
                {/* Endereços antigos do Meu Orçamento continuam funcionando. */}
                <Route path="/fixas" element={<Navigate to="/ajustes/recorrencias" replace />} />
                <Route path="/categorias" element={<Navigate to="/ajustes/categorias" replace />} />
                <Route path="/dados" element={<Navigate to="/ajustes/dados" replace />} />
                <Route path="/ajuda" element={<Navigate to="/ajustes/ajuda" replace />} />
                <Route path="/relatorio/ano/:ano" element={<AnnualReport />} />
                <Route path="/relatorio/:month?" element={<Report />} />
              </Route>
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </SolutionTransitionProvider>
    </BrowserRouter>
  );
}
