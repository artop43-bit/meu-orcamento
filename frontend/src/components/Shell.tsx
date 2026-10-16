import { useEffect, useLayoutEffect, useRef, useState, type MouseEvent, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeftRight,
  ChartPie,
  Ellipsis,
  History,
  Landmark,
  LogOut,
  RefreshCw,
  Repeat,
  ShieldAlert,
  ShieldCheck,
  Tags,
  Target,
  Wallet,
} from "lucide-react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router";

import { authApi, ME_KEY, useMe } from "../api/auth";
import { announce, prefersReducedMotion } from "../lib/announce";
import { neighbor } from "../lib/gestures";
import { haptic } from "../lib/haptics";
import { Brand, Sheet } from "./ui";
import { resetSwipe, useMobileGestures } from "./useMobileGestures";

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

const ALL = [...MAIN, ...SETTINGS];
const TITLES: Record<string, string> = Object.fromEntries(ALL.map((item) => [item.to, item.label]));
const TAB_PATHS = TABS.map((item) => item.to);

/**
 * Estrutura do app logado.
 * Desktop: menu lateral fixo. Celular: barra superior + abas embaixo + menu "Mais",
 * com gestos (deslizar entre abas, puxar para atualizar).
 */
export function Shell() {
  const queryClient = useQueryClient();
  const { data: user } = useMe();
  const location = useLocation();
  const navigate = useNavigate();
  const [moreOpen, setMoreOpen] = useState(false);
  const contentRef = useRef<HTMLElement>(null);
  const pageRef = useRef<HTMLDivElement>(null);
  const pullRef = useRef<HTMLDivElement>(null);
  const previousSection = useRef<string | null>(null);

  const section = "/" + (location.pathname.split("/")[1] ?? "");
  const title = TITLES[section] ?? "Meu Orçamento";
  const showTwoFactorBanner = user && !user.totp_enabled && location.pathname !== "/seguranca";
  const tabIndex = TAB_PATHS.indexOf(section);
  const inMore = MORE.some((item) => item.to === section);

  // Fecha o menu "Mais" ao trocar de página.
  useEffect(() => setMoreOpen(false), [location.pathname]);

  useEffect(() => {
    document.title = `${title} · Meu Orçamento`;
  }, [title]);

  // Troca de seção: animação de entrada na direção certa, volta ao topo e leva o foco
  // ao título (quem usa leitor de tela ou teclado fica sabendo que a página mudou).
  useLayoutEffect(() => {
    const from = previousSection.current;
    previousSection.current = section;
    resetSwipe(contentRef.current);
    if (from === null || from === section) return;
    const order = ALL.map((item) => item.to);
    const dir = Math.sign(order.indexOf(section) - order.indexOf(from));
    if (pageRef.current) pageRef.current.dataset.enter = String(dir);
    window.scrollTo(0, 0);
    const heading = pageRef.current?.querySelector("h1");
    if (heading) {
      heading.setAttribute("tabindex", "-1");
      heading.focus({ preventScroll: true });
    }
  }, [section]);

  useMobileGestures(contentRef, pullRef, {
    canGo: (dir) => neighbor(TAB_PATHS, tabIndex, dir) !== null,
    go: (dir) => {
      const to = neighbor(TAB_PATHS, tabIndex, dir);
      if (to) navigate(to);
    },
    refresh: async () => {
      await queryClient.refetchQueries({ type: "active" });
      haptic("success");
      announce("Dados atualizados");
    },
  });

  async function logout() {
    await authApi.logout().catch(() => undefined);
    queryClient.setQueryData(ME_KEY, null);
    queryClient.clear();
  }

  // Tocar de novo na aba em que já está volta ao topo (como nos apps nativos).
  function onNavClick(event: MouseEvent, to: string) {
    if (to === section && window.scrollY > 0) {
      event.preventDefault();
      window.scrollTo({ top: 0, behavior: prefersReducedMotion() ? "auto" : "smooth" });
    }
  }

  return (
    <div className="shell">
      <a href="#conteudo" className="skip-link">
        Pular para o conteúdo
      </a>
      <aside className="sidebar no-print" aria-label="Menu principal">
        <Brand to="/" />
        <nav className="stack stack--tight" style={{ gap: 2 }} aria-label="Seções">
          {MAIN.map((item) => (
            <NavLink key={item.to} to={item.to} className="sidebar__link" onClick={(e) => onNavClick(e, item.to)}>
              {item.icon}
              {item.label}
            </NavLink>
          ))}
          <p className="sidebar__group">Configurações</p>
          {SETTINGS.map((item) => (
            <NavLink key={item.to} to={item.to} className="sidebar__link" onClick={(e) => onNavClick(e, item.to)}>
              {item.icon}
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar__footer">
          <span className="sidebar__user" title={user?.email}>
            {user?.email}
          </span>
          <button type="button" className="sidebar__link sidebar__logout" onClick={logout}>
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

      <div className="shell__main">
        <header className="mobile-bar no-print">
          <strong style={{ fontSize: "1.1rem" }}>{title}</strong>
          <Link to="/" className="brand__logo" aria-label="Meu Orçamento, início">
            <Wallet size={18} />
          </Link>
        </header>

        <div ref={pullRef} className="pull no-print" aria-hidden>
          <RefreshCw size={18} />
        </div>

        <main ref={contentRef} id="conteudo" className="content" tabIndex={-1}>
          <div ref={pageRef} key={section} className="page">
            {showTwoFactorBanner && (
              <div className="banner no-print">
                <ShieldAlert size={18} />
                <span>
                  Proteja seus dados financeiros: <Link to="/seguranca">ative a verificação em duas etapas</Link>.
                </span>
              </div>
            )}
            <Outlet />
          </div>
        </main>
      </div>

      <nav className="tabbar no-print" aria-label="Navegação">
        {TABS.map((item) => (
          <NavLink key={item.to} to={item.to} onClick={(e) => onNavClick(e, item.to)}>
            {item.icon}
            {item.label}
          </NavLink>
        ))}
        <button
          type="button"
          className={inMore ? "active" : undefined}
          onClick={() => setMoreOpen(true)}
          aria-haspopup="dialog"
          aria-expanded={moreOpen}
          aria-current={inMore ? "page" : undefined}
        >
          <Ellipsis size={20} />
          Mais
        </button>
      </nav>

      <Sheet open={moreOpen} title="Mais opções" onClose={() => setMoreOpen(false)}>
        <ul className="menu-list">
          {MORE.map((item) => (
            <li key={item.to}>
              <Link to={item.to} aria-current={item.to === section ? "page" : undefined}>
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

      <div id="sr-announcer" className="sr-only" role="status" aria-live="polite" />
    </div>
  );
}
