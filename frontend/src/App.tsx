import { useQueryClient } from "@tanstack/react-query";
import { BrowserRouter, Link, Navigate, NavLink, Outlet, Route, Routes, useLocation } from "react-router";

import { authApi, ME_KEY, useMe } from "./api/auth";
import { errorMessage } from "./api/client";
import Analysis from "./pages/Analysis";
import Categories from "./pages/Categories";
import ForgotPassword from "./pages/ForgotPassword";
import Goals from "./pages/Goals";
import History from "./pages/History";
import Investments from "./pages/Investments";
import Login from "./pages/Login";
import MonthPage from "./pages/Month";
import RecurringPage from "./pages/Recurring";
import Register from "./pages/Register";
import ResetPassword from "./pages/ResetPassword";
import Security from "./pages/Security";
import VerifyEmail from "./pages/VerifyEmail";

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
  return <AppLayout />;
}

/** Páginas só para visitantes (login, cadastro): quem já entrou vai para o início. */
function GuestOnly() {
  const me = useMe();
  if (me.isPending) return <FullPageMessage>Carregando…</FullPageMessage>;
  if (me.data) return <Navigate to="/" replace />;
  return <Outlet />;
}

function AppLayout() {
  const queryClient = useQueryClient();
  const { data: user } = useMe();
  const location = useLocation();

  async function logout() {
    await authApi.logout().catch(() => undefined);
    queryClient.setQueryData(ME_KEY, null);
    queryClient.clear();
  }

  return (
    <>
      <header className="topbar">
        <Link to="/" className="brand">
          Meu Orçamento
        </Link>
        <nav>
          <NavLink to="/orcamento">Orçamento</NavLink>
          <NavLink to="/metas">Metas</NavLink>
          <NavLink to="/historico">Histórico</NavLink>
          <NavLink to="/analises">Análises</NavLink>
          <NavLink to="/investimentos">Investimentos</NavLink>
          <NavLink to="/fixas">Fixas</NavLink>
          <NavLink to="/categorias">Categorias</NavLink>
          <NavLink to="/seguranca">Segurança</NavLink>
          <button type="button" className="link" onClick={logout}>
            Sair
          </button>
        </nav>
      </header>
      <main className="container">
        {user && !user.totp_enabled && location.pathname !== "/seguranca" && (
          <div className="banner">
            Proteja seus dados financeiros: <Link to="/seguranca">ative a verificação em duas etapas</Link>.
          </div>
        )}
        <Outlet />
      </main>
    </>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<GuestOnly />}>
          <Route path="/entrar" element={<Login />} />
          <Route path="/cadastro" element={<Register />} />
          <Route path="/esqueci-senha" element={<ForgotPassword />} />
        </Route>
        {/* Acessíveis com ou sem login (abertas a partir de links de e-mail). */}
        <Route path="/verificar-email" element={<VerifyEmail />} />
        <Route path="/redefinir-senha" element={<ResetPassword />} />
        <Route element={<RequireAuth />}>
          <Route path="/" element={<Navigate to="/orcamento" replace />} />
          <Route path="/orcamento/:month?" element={<MonthPage />} />
          <Route path="/metas" element={<Goals />} />
          <Route path="/historico" element={<History />} />
          <Route path="/analises" element={<Analysis />} />
          <Route path="/investimentos" element={<Investments />} />
          <Route path="/fixas" element={<RecurringPage />} />
          <Route path="/categorias" element={<Categories />} />
          <Route path="/seguranca" element={<Security />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
