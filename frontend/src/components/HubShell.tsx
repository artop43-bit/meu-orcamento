import { useEffect, type MouseEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, LayoutGrid, LogOut, Mail, Monitor, Moon, Settings, ShieldCheck, Sun } from "lucide-react";
import { Link, Outlet, useLocation } from "react-router";

import { authApi, ME_KEY, useMe } from "../api/auth";
import { useInboxUnread } from "../api/inbox";
import { moneyApi } from "../api/money";
import { useProfile } from "../api/profile";
import { announce } from "../lib/announce";
import { nextTheme, originOf, setAppearance, syncAppearance, THEMES } from "../lib/appearance";
import { usePrefs } from "../lib/prefs";
import { preloadPages } from "../pages/lazy";
import { releaseLabel } from "../release";
import { TwoFactorBanner } from "./account";
import { Avatar } from "./media";
import { HubLayer } from "./power";
import { Brand } from "./ui";

const THEME_ICON = {
  system: <Monitor size={17} />,
  light: <Sun size={17} />,
  dark: <Moon size={17} />,
} as const;

type HubRouteMeta = { prefix: string; label: string; parentTo: string; parentLabel: string };

const HUB_ROUTES: HubRouteMeta[] = [
  { prefix: "/configuracoes", label: "Configurações", parentTo: "/", parentLabel: "Hub de Soluções" },
  { prefix: "/seguranca", label: "Segurança da conta", parentTo: "/configuracoes", parentLabel: "Configurações" },
  { prefix: "/preferencias", label: "Preferências", parentTo: "/configuracoes", parentLabel: "Configurações" },
  { prefix: "/app", label: "App e notificações", parentTo: "/configuracoes", parentLabel: "Configurações" },
  { prefix: "/notas", label: "Notas da versão", parentTo: "/configuracoes", parentLabel: "Configurações" },
  { prefix: "/perfil", label: "Perfil", parentTo: "/", parentLabel: "Hub de Soluções" },
  { prefix: "/mensagens", label: "Mensagens", parentTo: "/", parentLabel: "Hub de Soluções" },
  { prefix: "/admin", label: "Administração", parentTo: "/", parentLabel: "Hub de Soluções" },
];

/** Moldura do Hub de Soluções: barra superior da conta e saída da sessão. */
export function HubShell() {
  const queryClient = useQueryClient();
  const location = useLocation();
  const { data: user } = useMe();
  const profile = useProfile();
  const prefs = usePrefs();
  const inboxUnread = useInboxUnread(Boolean(user)).data ?? 0;
  const adminOverview = useQuery({
    queryKey: ["admin", "overview"],
    queryFn: moneyApi.adminOverview,
    enabled: Boolean(user?.is_admin),
    refetchInterval: 60_000,
  });
  const adminUnread = adminOverview.data?.feedback_new ?? 0;

  const isHome = location.pathname === "/";
  const current = HUB_ROUTES.find((item) => location.pathname.startsWith(item.prefix));

  useEffect(() => {
    document.title = current ? `${current.label} · Hub de Soluções` : "Hub de Soluções";
  }, [current]);

  useEffect(() => {
    if (user) syncAppearance(user);
  }, [user]);

  useEffect(() => preloadPages(), []);

  const displayName = profile.data?.display_name || user?.email || "";
  const themeLabel = THEMES.find(([value]) => value === prefs.theme)?.[1] ?? "Automático";

  function cycleTheme(event: MouseEvent<HTMLButtonElement>) {
    const theme = nextTheme(prefs.theme);
    setAppearance({ theme }, queryClient, originOf(event));
    announce(`Tema: ${THEMES.find(([value]) => value === theme)?.[1]}`);
  }

  async function logout() {
    await authApi.logout().catch(() => undefined);
    navigator.serviceWorker?.controller?.postMessage("limpar-dados");
    queryClient.setQueryData(ME_KEY, null);
    queryClient.clear();
  }

  return (
    <div className="hub">
      <a href="#conteudo" className="skip-link">
        Pular para o conteúdo
      </a>
      <header className="hub__bar">
        <div className="hub__bar-inner">
          <Brand to="/" label="Hub de Soluções" icon={<LayoutGrid size={18} />} />
          <div className="hub__actions">
            <Link to="/perfil" className="hub__account" title="Perfil">
              <Avatar fileId={profile.data?.avatar_id} name={displayName} size={28} />
              <span className="hub__account-name">{displayName}</span>
            </Link>
            <Link
              to="/mensagens"
              className="icon-btn icon-btn--badge"
              aria-label={inboxUnread > 0 ? `Mensagens, ${inboxUnread} não lida(s)` : "Mensagens"}
              title="Mensagens"
            >
              <Mail size={18} />
              {inboxUnread > 0 && <span className="icon-btn__dot" aria-hidden />}
            </Link>
            <Link to="/configuracoes" className="icon-btn" aria-label="Configurações" title="Configurações">
              <Settings size={18} />
            </Link>
            {user?.is_admin && (
              <Link
                to="/admin"
                className={`btn btn--secondary btn--sm hub__admin-link ${location.pathname.startsWith("/admin") ? "is-active" : ""}`}
                aria-label={
                  adminUnread > 0
                    ? `Administração, ${adminUnread} solicitação(ões) não lida(s)`
                    : "Administração"
                }
                title="Painel de Administração"
              >
                <ShieldCheck size={16} aria-hidden />
                <span className="hub__admin-label">Administração</span>
                {adminUnread > 0 && <span className="badge badge--accent">{adminUnread}</span>}
              </Link>
            )}
            <button
              type="button"
              className="icon-btn"
              onClick={cycleTheme}
              aria-label={`Tema: ${themeLabel}. Trocar o tema`}
              title={`Tema: ${themeLabel} (clique para trocar)`}
            >
              {THEME_ICON[prefs.theme]}
            </button>
            <button type="button" className="btn btn--secondary hub__logout" onClick={() => void logout()} aria-label="Sair">
              <LogOut size={16} aria-hidden />
              <span className="hub__logout-label">Sair</span>
            </button>
          </div>
        </div>
      </header>

      <main id="conteudo" className="hub__main">
        <TwoFactorBanner />
        {!isHome && current && (
          <nav className="breadcrumb no-print" aria-label="Você está em">
            <Link to={current.parentTo}>
              <ChevronLeft size={16} aria-hidden /> {current.parentLabel}
            </Link>
            <span aria-current="page"> / {current.label}</span>
          </nav>
        )}
        <Outlet />
      </main>

      <footer className="footer hub__footer">
        <Link to="/configuracoes">Configurações</Link>
        <Link to="/privacidade">Privacidade</Link>
        <Link to="/termos">Termos de uso</Link>
        <span className="muted">{releaseLabel("hub")}</span>
      </footer>
      <HubLayer />
      <div id="sr-announcer" className="sr-only" role="status" aria-live="polite" />
    </div>
  );
}
