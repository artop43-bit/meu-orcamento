import { useEffect, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeftRight,
  ChartPie,
  Ellipsis,
  History,
  Landmark,
  LogOut,
  Repeat,
  ShieldAlert,
  ShieldCheck,
  Tags,
  Target,
  Wallet,
} from "lucide-react";
import { Link, NavLink, Outlet, useLocation } from "react-router";

import { authApi, ME_KEY, useMe } from "../api/auth";
import { Brand, Sheet } from "./ui";

type NavItem = { to: string; label: string; icon: ReactNode };

const MAIN: NavItem[] = [
  { to: "/orcamento", label: "Orçamento", icon: <Wallet size={20} /> },
  { to: "/metas", label: "Metas", icon: <Target size={20} /> },
  { to: "/analises", label: "Análises", icon: <ChartPie size={20} /> },
  { to: "/investimentos", label: "Investimentos", icon: <Landmark size={20} /> },
  { to: "/historico", label: "Histórico", icon: <History size={20} /> },
];

const SETTINGS: NavItem[] = [
  { to: "/fixas", label: "Contas fixas", icon: <Repeat size={20} /> },
  { to: "/categorias", label: "Categorias", icon: <Tags size={20} /> },
  { to: "/dados", label: "Importar e exportar", icon: <ArrowLeftRight size={20} /> },
  { to: "/seguranca", label: "Segurança", icon: <ShieldCheck size={20} /> },
];

// No celular, as 4 primeiras viram abas; o resto vai para "Mais".
const TABS = MAIN.slice(0, 4);
const MORE = [...MAIN.slice(4), ...SETTINGS];

const TITLES: Record<string, string> = Object.fromEntries(
  [...MAIN, ...SETTINGS].map((item) => [item.to, item.label]),
);

/**
 * Estrutura do app logado.
 * Desktop: menu lateral fixo. Celular: barra superior + abas embaixo + menu "Mais".
 */
export function Shell() {
  const queryClient = useQueryClient();
  const { data: user } = useMe();
  const location = useLocation();
  const [moreOpen, setMoreOpen] = useState(false);

  // Fecha o menu "Mais" ao trocar de página.
  useEffect(() => setMoreOpen(false), [location.pathname]);

  async function logout() {
    await authApi.logout().catch(() => undefined);
    queryClient.setQueryData(ME_KEY, null);
    queryClient.clear();
  }

  const section = "/" + (location.pathname.split("/")[1] ?? "");
  const title = TITLES[section] ?? "Meu Orçamento";
  const showTwoFactorBanner = user && !user.totp_enabled && location.pathname !== "/seguranca";

  return (
    <div className="shell">
      <aside className="sidebar no-print" aria-label="Menu principal">
        <Brand to="/" />
        <nav className="stack stack--tight" style={{ gap: 2 }}>
          {MAIN.map((item) => (
            <NavLink key={item.to} to={item.to} className="sidebar__link">
              {item.icon}
              {item.label}
            </NavLink>
          ))}
          <p className="sidebar__group">Configurações</p>
          {SETTINGS.map((item) => (
            <NavLink key={item.to} to={item.to} className="sidebar__link">
              {item.icon}
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar__footer">
          <span className="sidebar__user" title={user?.email}>
            {user?.email}
          </span>
          <button type="button" className="sidebar__link" style={{ border: "none", background: "none", font: "inherit", cursor: "pointer", padding: "8px 0" }} onClick={logout}>
            <LogOut size={18} /> Sair
          </button>
          <span className="row small" style={{ gap: 12 }}>
            <Link to="/privacidade" className="muted">
              Privacidade
            </Link>
            <Link to="/termos" className="muted">
              Termos
            </Link>
          </span>
        </div>
      </aside>

      <div>
        <header className="mobile-bar no-print">
          <strong style={{ fontSize: "1.1rem" }}>{title}</strong>
          <Link to="/" className="brand__logo" aria-label="Meu Orçamento, início">
            <Wallet size={18} />
          </Link>
        </header>

        <main className="content">
          {showTwoFactorBanner && (
            <div className="banner no-print">
              <ShieldAlert size={18} />
              <span>
                Proteja seus dados financeiros: <Link to="/seguranca">ative a verificação em duas etapas</Link>.
              </span>
            </div>
          )}
          <Outlet />
        </main>
      </div>

      <nav className="tabbar no-print" aria-label="Navegação">
        {TABS.map((item) => (
          <NavLink key={item.to} to={item.to}>
            {item.icon}
            {item.label}
          </NavLink>
        ))}
        <button type="button" onClick={() => setMoreOpen(true)} aria-haspopup="dialog">
          <Ellipsis size={20} />
          Mais
        </button>
      </nav>

      <Sheet open={moreOpen} title="Mais opções" onClose={() => setMoreOpen(false)}>
        <ul className="menu-list">
          {MORE.map((item) => (
            <li key={item.to}>
              <Link to={item.to}>
                {item.icon}
                {item.label}
              </Link>
            </li>
          ))}
          <li>
            <button type="button" onClick={logout}>
              <LogOut size={20} /> Sair
            </button>
          </li>
        </ul>
        <p className="muted small" style={{ margin: "12px 0 0" }}>
          {user?.email} · <Link to="/privacidade">Privacidade</Link> · <Link to="/termos">Termos</Link>
        </p>
      </Sheet>
    </div>
  );
}
