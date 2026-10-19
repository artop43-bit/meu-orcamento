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
  Analysis,
  CalendarPage,
  Categories,
  DataPage,
  Goals,
  HelpPage,
  History,
  Investments,
  Privacy,
  RecurringPage,
  Report,
  Security,
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
        <Route element={<RequireAuth />}>
          <Route path="/" element={<Navigate to="/orcamento" replace />} />
          <Route path="/orcamento/:month?" element={<MonthPage />} />
          <Route path="/calendario/:month?" element={<CalendarPage />} />
          <Route path="/ajuda" element={<HelpPage />} />
          <Route path="/metas" element={<Goals />} />
          <Route path="/historico" element={<History />} />
          <Route path="/analises" element={<Analysis />} />
          <Route path="/investimentos" element={<Investments />} />
          <Route path="/fixas" element={<RecurringPage />} />
          <Route path="/categorias" element={<Categories />} />
          <Route path="/dados" element={<DataPage />} />
          <Route path="/relatorio/:month?" element={<Report />} />
          <Route path="/seguranca" element={<Security />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      </Suspense>
    </BrowserRouter>
  );
}
