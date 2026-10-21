import { Suspense, useEffect, useLayoutEffect, useRef, useState, type MouseEvent, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Banknote,
  CalendarDays,
  CalendarRange,
  ChartPie,
  ChevronDown,
  CreditCard,
  Ellipsis,
  Eye,
  EyeOff,
  History,
  Landmark,
  LogOut,
  Mail,
  MessageSquarePlus,
  Monitor,
  Moon,
  RefreshCw,
  Scale,
  Search,
  Settings,
  ShieldAlert,
  ShieldCheck,
  Sun,
  Target,
  Users,
  Wallet,
  WalletCards,
  WifiOff,
} from "lucide-react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router";

import { authApi, ME_KEY, useMe } from "../api/auth";
import { moneyApi } from "../api/money";
import { useProfile } from "../api/profile";
import { useInboxUnread } from "../api/inbox";
import { announce, prefersReducedMotion } from "../lib/announce";
import { GROUPS, groupEntry, groupOf, leafLabel, LEAVES, MOBILE_TABS, neighborLeaf, parentOf, sectionOf, type NavGroup } from "../lib/navigation";
import { haptic } from "../lib/haptics";
import { prefetchProps } from "../lib/prefetch";
import { setCycleStart } from "../lib/format";
import { releaseLabel } from "../release";
import { Tour } from "./help";
import { Avatar } from "./media";
import { openFeedback, openPalette, PowerLayer } from "./power";
import { nextTheme, setAppearance, syncAppearance, THEMES } from "../lib/appearance";
import { togglePrivacy, usePrefs } from "../lib/prefs";
import { Brand, LoadingRegion, Sheet, Skeleton } from "./ui";
import { UndoProvider } from "./undo";
import { ErrorBoundary } from "./ErrorBoundary";
import { OnboardingPage, preloadPages } from "../pages/lazy";
import { resetSwipe, useMobileGestures } from "./useMobileGestures";

const OPEN_GROUPS_KEY = "menu-grupos-abertos";
const lastLeaf = new Map<string, string>();

function readOpenGroups(current?: string): string[] {
  let open: string[] = [];
  try {
    const saved = JSON.parse(localStorage.getItem(OPEN_GROUPS_KEY) ?? "[]");
    if (Array.isArray(saved)) open = saved.filter((k): k is string => typeof k === "string");
  } catch {
    // Sem acesso ao armazenamento (janela privada): começa só com o grupo da tela atual.
  }
  return current && !open.includes(current) ? [...open, current] : open;
}

function saveOpenGroups(open: string[]) {
  try {
    localStorage.setItem(OPEN_GROUPS_KEY, JSON.stringify(open));
  } catch {
    // Sem armazenamento: o menu só não lembra na próxima visita.
  }
}

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

type NavItem = { to: string; label: string; icon: ReactNode };

const GROUP_ICONS: Record<string, ReactNode> = {
  orcamento: <Wallet size={20} />,
  carteira: <WalletCards size={20} />,
  planejamento: <CalendarRange size={20} />,
  investimentos: <Landmark size={20} />,
  analises: <ChartPie size={20} />,
};
const LEAF_ICONS: Record<string, ReactNode> = {
  "/contas": <Banknote size={18} />,
  "/cartoes": <CreditCard size={18} />,
  "/dividas": <Scale size={18} />,
  "/divisoes": <Users size={18} />,
  "/calendario": <CalendarDays size={18} />,
  "/metas": <Target size={18} />,
  "/analises": <ChartPie size={18} />,
  "/historico": <History size={18} />,
};

const SETTINGS: NavItem = { to: "/ajustes", label: "Ajustes", icon: <Settings size={20} /> };
const THEME_ICON = { system: <Monitor size={17} />, light: <Sun size={17} />, dark: <Moon size={17} /> } as const;
const ADMIN: NavItem = { to: "/admin", label: "Administração", icon: <ShieldCheck size={20} /> };
// Telas fora dos grupos (títulos da barra do topo e do navegador).
const EXTRA_TITLES: Record<string, string> = {
  "/revisar": "Para revisar",
  "/busca": "Busca",
  "/admin": "Administração",
  "/mensagens": "Mensagens",
  "/ajustes": "Ajustes",
};

// No celular, os grupos principais viram abas; Investimentos fica no "Mais".
const TAB_GROUPS = GROUPS.filter((g) => MOBILE_TABS.includes(g.key));
const MORE_GROUPS = GROUPS.filter((g) => !MOBILE_TABS.includes(g.key));
const ORDER = [...LEAVES, "/ajustes"];
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
/** Sem internet: o app mostra os últimos dados salvos (service worker) e avisa. */
function useOffline(): boolean {
  const [offline, setOffline] = useState(() => typeof navigator !== "undefined" && navigator.onLine === false);
  useEffect(() => {
    const on = () => setOffline(false);
    const off = () => setOffline(true);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
    };
  }, []);
  return offline;
}

/** Contador discreto ao lado de um item do menu (respostas novas, solicitações não lidas). */
function NavBadge({ count, label }: { count: number; label: string }) {
  if (count <= 0) return null;
  return (
    <span className="nav-badge" aria-label={label} title={label}>
      {count > 9 ? "9+" : count}
    </span>
  );
}

export function Shell() {
  const queryClient = useQueryClient();
  const { data: user } = useMe();
  // Mês financeiro da conta: definido antes de as telas calcularem o "mês atual".
  setCycleStart(user?.month_start_day ?? 1);
  const location = useLocation();
  const navigate = useNavigate();
  const [moreOpen, setMoreOpen] = useState(false);
  const prefs = usePrefs();
  const contentRef = useRef<HTMLElement>(null);
  const pageRef = useRef<HTMLDivElement>(null);
  const pullRef = useRef<HTMLDivElement>(null);
  const previousSection = useRef<string | null>(null);

  const section = sectionOf(location.pathname);
  const title = leafLabel(location.pathname) ?? EXTRA_TITLES[section] ?? "Meu Orçamento";
  const group = groupOf(location.pathname);
  // Grupos abertos no menu: vários ao mesmo tempo, lembrados neste aparelho.
  const [openGroups, setOpenGroups] = useState<string[]>(() => readOpenGroups(group?.key));
  const [twoFactorLater, setTwoFactorLater] = useState(() => readSession(LATER_KEY));
  const showTwoFactorBanner =
    user && !user.totp_enabled && !user.twofa_prompt_dismissed && !twoFactorLater && location.pathname !== "/seguranca";
  const inMore = !group || !MOBILE_TABS.includes(group.key);

  // Depois de entrar, baixa as outras telas em segundo plano (navegação instantânea).
  useEffect(() => preloadPages(), []);

  // Aparência salva na conta vale também neste aparelho.
  useEffect(() => {
    if (user) syncAppearance(user);
  }, [user]);

  // Fecha o menu "Mais" ao trocar de página; o grupo da tela atual fica aberto no menu.
  useEffect(() => setMoreOpen(false), [location.pathname]);
  useEffect(() => {
    if (group?.children) setOpenGroups((open) => (open.includes(group.key) ? open : [...open, group.key]));
  }, [group]);
  useEffect(() => saveOpenGroups(openGroups), [openGroups]);
  // Última tela visitada em cada grupo: a aba de baixo (celular) volta para ela.
  useEffect(() => {
    if (group?.children) lastLeaf.set(group.key, section);
  }, [group, section]);

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
    const dir = Math.sign(ORDER.indexOf(section) - ORDER.indexOf(from));
    if (pageRef.current) pageRef.current.dataset.enter = String(dir);
    window.scrollTo(0, 0);
    const heading = pageRef.current?.querySelector("h1");
    if (heading) {
      heading.setAttribute("tabindex", "-1");
      heading.focus({ preventScroll: true });
    }
  }, [section]);

  // Deslizar anda pelas telas na ordem do menu; numa sub-tela (ex.: Ajustes › Perfil),
  // deslizar para a direita volta para a tela de cima.
  const parent = parentOf(location.pathname);
  useMobileGestures(contentRef, pullRef, {
    canGo: (dir) => (dir === -1 && parent !== null) || (parent === null && neighborLeaf(location.pathname, dir) !== null),
    go: (dir) => {
      const to = dir === -1 && parent !== null ? parent : neighborLeaf(location.pathname, dir);
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
    announce("Lembrete desativado. A verificação pode ser ativada em Ajustes, Segurança.");
    await authApi.setTwoFactorPrompt(true).catch(() => undefined);
  }

  const inboxUnread = useInboxUnread(Boolean(user)).data ?? 0;
  const offline = useOffline();
  const profile = useProfile();
  const adminOverview = useQuery({
    queryKey: ["admin", "overview"],
    queryFn: moneyApi.adminOverview,
    enabled: Boolean(user?.is_admin),
    refetchInterval: 60_000,
  });
  const adminUnread = adminOverview.data?.feedback_new ?? 0;
  const displayName = profile.data?.display_name || user?.email || "";
  const unreadLabel = `${inboxUnread} mensagem(ns) não lida(s)`;
  const themeLabel = THEMES.find(([value]) => value === prefs.theme)?.[1] ?? "Automático";
  const cycleTheme = () => {
    const theme = nextTheme(prefs.theme);
    setAppearance({ theme }, queryClient);
    announce(`Tema: ${THEMES.find(([value]) => value === theme)?.[1]}`);
  };

  async function logout() {
    await authApi.logout().catch(() => undefined);
    // Dados guardados para uso sem internet ficam só enquanto a pessoa está logada.
    navigator.serviceWorker?.controller?.postMessage("limpar-dados");
    queryClient.setQueryData(ME_KEY, null);
    queryClient.clear();
  }

  // Grupo do menu: só abre ou fecha (sem trocar de tela); vários podem ficar abertos.
  function toggleGroup(g: NavGroup) {
    setOpenGroups((open) => (open.includes(g.key) ? open.filter((k) => k !== g.key) : [...open, g.key]));
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
          {GROUPS.map((g) =>
            g.children ? (
              <div key={g.key} className={`nav-group ${group?.key === g.key ? "is-current" : ""}`}>
                <button
                  type="button"
                  className="sidebar__link nav-group__toggle"
                  aria-expanded={openGroups.includes(g.key)}
                  aria-controls={`grupo-${g.key}`}
                  onClick={() => toggleGroup(g)}
                >
                  {GROUP_ICONS[g.key]}
                  {g.label}
                  <ChevronDown size={16} className="nav-group__chevron" aria-hidden />
                </button>
                {openGroups.includes(g.key) && (
                  <div id={`grupo-${g.key}`} className="nav-group__items">
                    {g.children.map((c) => (
                      <NavLink
                        key={c.to}
                        to={c.to}
                        className="sidebar__link sidebar__sublink"
                        onClick={(e) => onNavClick(e, c.to)}
                        {...prefetchProps(queryClient, c.to)}
                      >
                        {LEAF_ICONS[c.to]}
                        {c.label}
                      </NavLink>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <NavLink key={g.key} to={g.to!} className="sidebar__link" onClick={(e) => onNavClick(e, g.to!)} {...prefetchProps(queryClient, g.to!)}>
                {GROUP_ICONS[g.key]}
                {g.label}
              </NavLink>
            ),
          )}
          <p className="sidebar__group" aria-hidden></p>
          <NavLink to={SETTINGS.to} className="sidebar__link" onClick={(e) => onNavClick(e, SETTINGS.to)}>
            {SETTINGS.icon}
            {SETTINGS.label}
          </NavLink>
          {user?.is_admin && (
            <NavLink to="/admin" className="sidebar__link">
              {ADMIN.icon}
              {ADMIN.label}
              <NavBadge count={adminUnread} label={`${adminUnread} solicitação(ões) não lida(s)`} />
            </NavLink>
          )}
        </nav>
        <div className="sidebar__tools" role="toolbar" aria-label="Ferramentas">
          <button type="button" className="sidebar__tool sidebar__tool--wide" onClick={openPalette} title="Buscar ou lançar (Ctrl+K)">
            <Search size={17} aria-hidden /> <span>Buscar</span>
          </button>
          <button
            type="button"
            className="sidebar__tool"
            onClick={() => togglePrivacy()}
            aria-pressed={prefs.privacy}
            aria-label={prefs.privacy ? "Mostrar valores" : "Esconder valores"}
            title={prefs.privacy ? "Mostrar valores (P)" : "Esconder valores (P)"}
          >
            {prefs.privacy ? <Eye size={17} /> : <EyeOff size={17} />}
          </button>
          <NavLink
            to="/mensagens"
            className="sidebar__tool sidebar__tool--messages"
            aria-label={inboxUnread > 0 ? `Mensagens, ${unreadLabel}` : "Mensagens"}
            title="Mensagens"
          >
            <Mail size={17} />
            {inboxUnread > 0 && (
              <span className="sidebar__tool-badge" aria-hidden>
                {inboxUnread > 9 ? "9+" : inboxUnread}
              </span>
            )}
          </NavLink>
          <button type="button" className="sidebar__tool" onClick={openFeedback} aria-label="Nova solicitação" title="Nova solicitação (sugestão ou problema)">
            <MessageSquarePlus size={17} />
          </button>
        </div>
        <div className="sidebar__footer">
          <Link to="/ajustes/perfil" className="sidebar__profile" title="Meu perfil">
            <Avatar fileId={profile.data?.avatar_id} name={displayName} size={32} />
            <span className="sidebar__user">
              <strong>{displayName}</strong>
              {profile.data?.display_name && <span className="muted small">{user?.email}</span>}
            </span>
          </Link>
          <div className="sidebar__footer-row">
            <button type="button" className="sidebar__link sidebar__logout" onClick={logout}>
              <LogOut size={18} /> Sair
            </button>
            <button
              type="button"
              className="sidebar__tool sidebar__theme"
              onClick={cycleTheme}
              aria-label={`Tema: ${themeLabel}. Trocar o tema`}
              title={`Tema: ${themeLabel} (clique para trocar)`}
            >
              {THEME_ICON[prefs.theme]}
            </button>
          </div>
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
          <span className="row" style={{ gap: 4 }}>
            <button type="button" className="icon-btn" onClick={() => togglePrivacy()} aria-pressed={prefs.privacy} aria-label={prefs.privacy ? "Mostrar valores" : "Esconder valores"}>
              {prefs.privacy ? <Eye size={18} /> : <EyeOff size={18} />}
            </button>
            <button type="button" className="icon-btn" onClick={openPalette} aria-label="Buscar ou lançar">
              <Search size={18} />
            </button>
            <Link to="/mensagens" className="icon-btn icon-btn--badge" aria-label={inboxUnread > 0 ? `Mensagens, ${unreadLabel}` : "Mensagens"}>
              <Mail size={18} />
              {inboxUnread > 0 && <span className="icon-btn__dot" aria-hidden />}
            </Link>
            <Link to="/" className="brand__logo" aria-label="Meu Orçamento, início">
              <Wallet size={18} />
            </Link>
          </span>
        </header>

        <div ref={pullRef} className="pull no-print" aria-hidden>
          <RefreshCw size={18} />
        </div>

        <main ref={contentRef} id="conteudo" className="content" tabIndex={-1}>
          <div ref={pageRef} key={section} className="page">
            {offline && (
              <div className="banner banner--offline no-print" role="status">
                <WifiOff size={18} />
                <span>Sem conexão. Mostrando os últimos dados salvos neste aparelho; para salvar alterações, conecte-se à internet.</span>
              </div>
            )}
            {showTwoFactorBanner && (
              <div className="banner no-print" role="region" aria-label="Sugestão de segurança">
                <ShieldAlert size={18} />
                <span>
                  Recomendado: <Link to="/ajustes/seguranca">ative a verificação em duas etapas</Link> para proteger o acesso.
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
            {group?.children && (
              <nav className="group-tabs no-print" aria-label={group.label}>
                {group.children.map((c) => (
                  <NavLink key={c.to} to={c.to} {...prefetchProps(queryClient, c.to)}>
                    {c.label}
                  </NavLink>
                ))}
              </nav>
            )}
            {/* A chave inclui a privacidade: ao esconder/mostrar valores, a tela redesenha. */}
            <ErrorBoundary key={`${location.pathname}-${prefs.privacy}`}>
              <Suspense fallback={<PageLoading />}>
                <Outlet />
              </Suspense>
            </ErrorBoundary>
          </div>
        </main>
      </div>

      <nav className="tabbar no-print" aria-label="Navegação">
        {TAB_GROUPS.map((g) => {
          const active = group?.key === g.key;
          const to = active ? section : (lastLeaf.get(g.key) ?? groupEntry(g));
          return (
            <Link
              key={g.key}
              to={to}
              className={active ? "active" : undefined}
              aria-current={active ? "page" : undefined}
              onClick={(e) => onNavClick(e, to)}
              {...prefetchProps(queryClient, to)}
            >
              {GROUP_ICONS[g.key]}
              {g.label}
            </Link>
          );
        })}
        <button
          type="button"
          className={inMore ? "active" : undefined}
          onClick={() => setMoreOpen(true)}
          aria-haspopup="dialog"
          aria-expanded={moreOpen}
          aria-current={inMore ? "page" : undefined}
        >
          <span className="tabbar__icon">
            <Ellipsis size={20} />
            {inboxUnread + adminUnread > 0 && <span className="tabbar__dot" aria-hidden />}
          </span>
          Mais
          {inboxUnread + adminUnread > 0 && <span className="sr-only"> (há mensagens novas)</span>}
        </button>
      </nav>

      <Sheet open={moreOpen} title="Mais opções" onClose={() => setMoreOpen(false)}>
        <Link to="/ajustes/perfil" className="menu-profile" onClick={() => setMoreOpen(false)}>
          <Avatar fileId={profile.data?.avatar_id} name={displayName} size={44} />
          <span>
            <strong>{displayName}</strong>
            <span className="muted small">Ver meu perfil</span>
          </span>
        </Link>
        <ul className="menu-list">
          {MORE_GROUPS.map((g) => (
            <li key={g.key}>
              <Link to={groupEntry(g)} aria-current={group?.key === g.key ? "page" : undefined}>
                {GROUP_ICONS[g.key]}
                {g.label}
              </Link>
            </li>
          ))}
          <li>
            <Link to="/mensagens" aria-current={section === "/mensagens" ? "page" : undefined}>
              <Mail size={20} />
              Mensagens
              <NavBadge count={inboxUnread} label={unreadLabel} />
            </Link>
          </li>
          <li>
            <Link to={SETTINGS.to} aria-current={section === SETTINGS.to ? "page" : undefined}>
              {SETTINGS.icon}
              {SETTINGS.label}
            </Link>
          </li>
          {user?.is_admin && (
            <li>
              <Link to="/admin">
                {ADMIN.icon}
                {ADMIN.label}
                <NavBadge count={adminUnread} label={`${adminUnread} solicitação(ões) não lida(s)`} />
              </Link>
            </li>
          )}
          <li>
            <fieldset className="radios menu-theme">
              <legend className="field-label">Tema</legend>
              <div className="segmented">
                {THEMES.map(([value, label]) => (
                  <label key={value}>
                    <input type="radio" name="menu-theme" checked={prefs.theme === value} onChange={() => setAppearance({ theme: value }, queryClient)} />
                    {label}
                  </label>
                ))}
              </div>
            </fieldset>
          </li>
          <li>
            <button type="button" onClick={openFeedback}>
              <MessageSquarePlus size={20} /> Nova solicitação
            </button>
          </li>
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

      {user && !user.onboarded_at ? (
        <Suspense fallback={null}>
          <OnboardingPage onClose={() => undefined} />
        </Suspense>
      ) : (
        <Tour />
      )}
      <PowerLayer />
      <div id="sr-announcer" className="sr-only" role="status" aria-live="polite" />
    </div>
    </UndoProvider>
  );
}
