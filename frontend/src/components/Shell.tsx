import { Suspense, useEffect, useLayoutEffect, useRef, useState, type MouseEvent, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeftRight,
  CalendarDays,
  ChartPie,
  CircleHelp,
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
import { releaseLabel } from "../release";
import { Tour } from "./help";
import { Brand, LoadingRegion, Sheet, Skeleton } from "./ui";
import { UndoProvider } from "./undo";
import { ErrorBoundary } from "./ErrorBoundary";
import { preloadPages } from "../pages/lazy";
import { resetSwipe, useMobileGestures } from "./useMobileGestures";

/** Enquanto a tela é baixada (primeira visita, conexão lenta). */
function PageLoading() {
  return (
    <LoadingRegion label="Carregando a tela">
      <div className="stack">
        <Skeleton height={34} width="45%" />
        <Skeleton height={160} />
        <Skeleton height={220} />
      </div>
    </LoadingRegion>
  );
}

type NavItem = { to: string; label: string; icon: ReactNode; short?: string };

const MAIN: NavItem[] = [
  { to: "/orcamento", label: "Orçamento", icon: <Wallet size={20} /> },
  { to: "/calendario", label: "Calendário", icon: <CalendarDays size={20} /> },
  { to: "/analises", label: "Análise financeira", short: "Análises", icon: <ChartPie size={20} /> },
  { to: "/investimentos", label: "Investimentos", icon: <Landmark size={20} /> },
  { to: "/metas", label: "Metas", icon: <Target size={20} /> },
  { to: "/historico", label: "Histórico", icon: <History size={20} /> },
];

const SETTINGS: NavItem[] = [
  { to: "/fixas", label: "Contas fixas", icon: <Repeat size={20} /> },
  { to: "/categorias", label: "Categorias", icon: <Tags size={20} /> },
  { to: "/dados", label: "Importar e exportar", icon: <ArrowLeftRight size={20} /> },
  { to: "/seguranca", label: "Segurança", icon: <ShieldCheck size={20} /> },
  { to: "/ajuda", label: "Como usar", icon: <CircleHelp size={20} /> },
];

// No celular, as 4 primeiras viram abas; o resto vai para "Mais".
const TABS = MAIN.slice(0, 4);
const MORE = [...MAIN.slice(4), ...SETTINGS];

const ALL = [...MAIN, ...SETTINGS];
const TITLES: Record<string, string> = Object.fromEntries(ALL.map((item) => [item.to, item.label]));
const TAB_PATHS = TABS.map((item) => item.to);
const LATER_KEY = "2fa-lembrar-depois";

function readSession(key: string): boolean {
  try {
    return sessionStorage.getItem(key) === "1";
  } catch {
    return false;
  }
}

function writeSession(key: string) {
  try {
    sessionStorage.setItem(key, "1");
  } catch {
    // Navegação privada sem armazenamento: o aviso some só nesta tela.
  }
}

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
  const [twoFactorLater, setTwoFactorLater] = useState(() => readSession(LATER_KEY));
  const showTwoFactorBanner =
    user && !user.totp_enabled && !user.twofa_prompt_dismissed && !twoFactorLater && location.pathname !== "/seguranca";
  const tabIndex = TAB_PATHS.indexOf(section);
  const inMore = MORE.some((item) => item.to === section);

  // Depois de entrar, baixa as outras telas em segundo plano (navegação instantânea).
  useEffect(() => preloadPages(), []);

  // Fecha o menu "Mais" ao trocar de página.
  useEffect(() => setMoreOpen(false), [location.pathname]);

  useEffect(() => {
    document.title = `${title} · Meu Orçamento`;
  }, [title]);

  // "Título grande" (como no iOS/Android): o título fica grande na página e só aparece
  // na barra do topo quando ele sai da tela ao rolar.
  const [condensed, setCondensed] = useState(false);
  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") {
      setCondensed(true);
      return;
    }
    const observer = new IntersectionObserver(([entry]) => setCondensed(!entry.isIntersecting), {
      rootMargin: "-56px 0px 0px 0px",
    });
    // A tela pode ainda estar sendo baixada: espera o título aparecer (até ~3 s).
    let tries = 0;
    let timer = 0;
    const attach = () => {
      const heading = pageRef.current?.querySelector("h1");
      if (heading) observer.observe(heading);
      else if (tries++ < 30) timer = window.setTimeout(attach, 100);
      else setCondensed(true);
    };
    attach();
    return () => {
      window.clearTimeout(timer);
      observer.disconnect();
    };
  }, [location.pathname, location.search]);

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

  // Deslizar sempre troca as abas principais (as seções dentro de cada tela são por toque).
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

  // "Agora não": some até fechar o navegador. "Não mostrar mais": fica salvo na conta
  // (dá para ativar a qualquer momento em Segurança).
  function remindLater() {
    writeSession(LATER_KEY);
    setTwoFactorLater(true);
  }

  async function dismissTwoFactor() {
    if (user) queryClient.setQueryData(ME_KEY, { ...user, twofa_prompt_dismissed: true });
    announce("Tudo bem. Você pode ativar quando quiser em Segurança.");
    await authApi.setTwoFactorPrompt(true).catch(() => undefined);
  }

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
    <UndoProvider>
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
          <span className="app-version" title="Versão do Meu Orçamento">
            {releaseLabel()}
          </span>
        </div>
      </aside>

      <div className="shell__main">
        <header className={`mobile-bar no-print ${condensed ? "is-condensed" : ""}`}>
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
              <div className="banner no-print" role="region" aria-label="Sugestão de segurança">
                <ShieldAlert size={18} />
                <span>
                  Recomendado: <Link to="/seguranca">ative a verificação em duas etapas</Link> para proteger sua conta.
                </span>
                <span className="banner__actions">
                  <button type="button" onClick={remindLater}>
                    Agora não
                  </button>
                  <button type="button" onClick={dismissTwoFactor}>
                    Não mostrar mais
                  </button>
                </span>
              </div>
            )}
            <ErrorBoundary key={location.pathname}>
              <Suspense fallback={<PageLoading />}>
                <Outlet />
              </Suspense>
            </ErrorBoundary>
          </div>
        </main>
      </div>

      <nav className="tabbar no-print" aria-label="Navegação">
        {TABS.map((item) => (
          <NavLink key={item.to} to={item.to} onClick={(e) => onNavClick(e, item.to)}>
            {item.icon}
            {item.short ?? item.label}
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
        <p className="app-version" style={{ margin: "8px 0 0" }}>
          {releaseLabel()}
        </p>
      </Sheet>

      <Tour />
      <div id="sr-announcer" className="sr-only" role="status" aria-live="polite" />
    </div>
    </UndoProvider>
  );
}
