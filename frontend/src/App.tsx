import { Suspense } from "react";
import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from "react-router";

import { useMe } from "./api/auth";
import { errorMessage } from "./api/client";
import { Shell } from "./components/Shell";
import ForgotPassword from "./pages/ForgotPassword";
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
  DataPage,
  Goals,
  HelpPage,
  History,
  Investments,
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
  LoanTablePage,
  Unsubscribe,
  Security,
  SettingsHub,
  SettingsLayout,
  ShortcutsPage,
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
  return <Shell />;
}

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
      <Suspense fallback={<FullPageMessage>Carregando…</FullPageMessage>}>
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
          <Route path="/" element={<Navigate to="/orcamento" replace />} />
          <Route path="/orcamento/:month?" element={<MonthPage />} />
          <Route path="/calendario/:month?" element={<CalendarPage />} />
          <Route path="/cartoes" element={<CardsPage />} />
          <Route path="/contas" element={<AccountsPage />} />
          <Route path="/revisar" element={<ReviewPage />} />
          <Route path="/busca" element={<SearchPage />} />
          <Route path="/mensagens" element={<InboxPage />} />
          <Route path="/dividas" element={<DebtsPage />} />
          <Route path="/divisoes" element={<SplitsPage />} />
          <Route path="/dividas/:id/tabela" element={<LoanTablePage />} />
          <Route path="/admin" element={<AdminPage />} />
          <Route path="/admin/sugestoes" element={<Navigate to="/admin?aba=solicitacoes" replace />} />
          <Route path="/metas" element={<Goals />} />
          <Route path="/historico" element={<History />} />
          <Route path="/analises" element={<Analysis />} />
          <Route path="/investimentos" element={<Investments />} />
          <Route path="/ajustes" element={<SettingsLayout />}>
            <Route index element={<SettingsHub />} />
            <Route path="recorrencias" element={<RecurringPage />} />
            <Route path="categorias" element={<Categories />} />
            <Route path="dados" element={<DataPage />} />
            <Route path="seguranca" element={<Security />} />
            <Route path="preferencias" element={<PreferencesPage />} />
            <Route path="atalhos" element={<ShortcutsPage />} />
            <Route path="perfil" element={<ProfilePage />} />
            <Route path="solicitacoes" element={<SupportPage />} />
            <Route path="solicitacoes/:id" element={<SupportPage />} />
            <Route path="ajuda" element={<HelpPage />} />
            <Route path="notas" element={<ReleaseNotesPage />} />
            <Route path="app" element={<AppInstallPage />} />
          </Route>
          {/* Endereços antigos continuam funcionando. */}
          <Route path="/fixas" element={<Navigate to="/ajustes/recorrencias" replace />} />
          <Route path="/categorias" element={<Navigate to="/ajustes/categorias" replace />} />
          <Route path="/dados" element={<Navigate to="/ajustes/dados" replace />} />
          <Route path="/seguranca" element={<Navigate to="/ajustes/seguranca" replace />} />
          <Route path="/preferencias" element={<Navigate to="/ajustes/preferencias" replace />} />
          <Route path="/ajuda" element={<Navigate to="/ajustes/ajuda" replace />} />
          <Route path="/relatorio/ano/:ano" element={<AnnualReport />} />
          <Route path="/relatorio/:month?" element={<Report />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      </Suspense>
    </BrowserRouter>
  );
}
