import { useEffect, useSyncExternalStore, type ComponentType, type MouseEvent, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { LogOut, Monitor, Moon, Sun } from "lucide-react";
import { NavLink, Outlet } from "react-router";

import { useMe } from "../api/auth";
import { announce } from "../lib/announce";
import { nextTheme, originOf, setAppearance, syncAppearance, THEMES } from "../lib/appearance";
import type { SolutionIcon as SolutionIconKey } from "../lib/hub";
import { usePrefs } from "../lib/prefs";
import type { ReleaseSolutionId } from "../lib/releases";
import { preloadPages } from "../pages/lazy";
import { releaseLabel } from "../release";
import { ErrorBoundary } from "./ErrorBoundary";
import { HubLayer } from "./power";
import { SolutionIcon } from "./SolutionIcon";
import { useLeaveSolution } from "./SolutionTransition";
import { Brand } from "./ui";
import { UndoProvider } from "./undo";

const THEME_ICON = {
  system: <Monitor size={17} aria-hidden />,
  light: <Sun size={17} aria-hidden />,
  dark: <Moon size={17} aria-hidden />,
} as const;

function subscribeOnline(cb: () => void) {
  window.addEventListener("online", cb);
  window.addEventListener("offline", cb);
  return () => {
    window.removeEventListener("online", cb);
    window.removeEventListener("offline", cb);
  };
}

function useOnline(): boolean {
  return useSyncExternalStore(
    subscribeOnline,
    () => typeof navigator === "undefined" || navigator.onLine !== false,
    () => true,
  );
}

export type SolutionNavItem = {
  to: string;
  label: string;
  icon: ComponentType<{ size?: number }>;
  end?: boolean;
};

/**
 * Moldura única reutilizável de todas as soluções integradas do Hub
 * (Meu Orçamento usa Shell próprio; Mensageria, Dashboard & CRM, Catálogo,
 * Propostas, Projetos e Agenda compartilham esta estrutura).
 */
export function SolutionShell({
  solutionId,
  releaseId,
  icon,
  name,
  homeTo,
  nav = [],
  variant = "crm",
  showVersionBadge = true,
  extraActions,
  footer,
  outletContext,
  children,
}: {
  solutionId: string;
  releaseId: ReleaseSolutionId;
  icon: SolutionIconKey;
  name: string;
  homeTo: string;
  nav?: readonly SolutionNavItem[];
  variant?: "crm" | "wa";
  showVersionBadge?: boolean;
  extraActions?: ReactNode;
  footer?: ReactNode;
  outletContext?: unknown;
  children?: ReactNode;
}) {
  const queryClient = useQueryClient();
  const leave = useLeaveSolution();
  const online = useOnline();
  const { data: user } = useMe();
  const prefs = usePrefs();
  const prefix = variant === "wa" ? "wa" : "crm";

  useEffect(() => {
    document.title = `${name} · Hub de Soluções`;
  }, [name]);

  useEffect(() => {
    if (user) syncAppearance(user);
  }, [user]);

  useEffect(() => preloadPages(), []);

  const themeLabel = THEMES.find(([value]) => value === prefs.theme)?.[1] ?? "Automático";

  function cycleTheme(event: MouseEvent<HTMLButtonElement>) {
    const theme = nextTheme(prefs.theme);
    setAppearance({ theme }, queryClient, originOf(event));
    announce(`Tema: ${THEMES.find(([value]) => value === theme)?.[1]}`);
  }

  return (
    <div className={`${prefix}-shell`} data-solution-root={solutionId}>
      <a href="#conteudo" className="skip-link">
        Pular para o conteúdo
      </a>

      <header className={`${prefix}-bar`}>
        <div className={`${prefix}-bar__inner`}>
          <Brand to={homeTo} label={name} icon={<SolutionIcon icon={icon} size={18} />} />

          {nav.length > 0 && (
            <nav className="crm-nav" aria-label={`Navegação de ${name}`}>
              {nav.map((item) => {
                const Icon = item.icon;
                return (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.end}
                    className={({ isActive }) => `crm-nav__link ${isActive ? "is-active" : ""}`}
                  >
                    <Icon size={16} aria-hidden />
                    <span>{item.label}</span>
                  </NavLink>
                );
              })}
            </nav>
          )}

          <div className={`${prefix}-bar__actions`}>
            {extraActions}
            {!online && (
              <span className="badge badge--warn" title="Sem conexão no momento">
                Offline
              </span>
            )}
            {showVersionBadge && (
              <span className="badge badge--muted small crm-bar__version" title={releaseLabel(releaseId)}>
                v{releaseLabel(releaseId).replace(/^Versão\s+/i, "")}
              </span>
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
            <button
              type="button"
              className="btn btn--secondary hub__logout"
              onClick={leave}
              aria-label="Sair"
              title="Voltar ao Hub de Soluções"
            >
              <LogOut size={16} aria-hidden />
              <span className="hub__logout-label">Sair</span>
            </button>
          </div>
        </div>
      </header>

      <main className={`${prefix}-main`} id="conteudo">
        <UndoProvider>
          <ErrorBoundary>
            <Outlet context={outletContext} />
          </ErrorBoundary>
        </UndoProvider>
        {variant === "crm" && footer}
      </main>

      {nav.length > 1 && (
        <nav className="crm-tabbar" aria-label={`Atalhos de ${name}`}>
          {nav.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) => `crm-tabbar__item ${isActive ? "is-active" : ""}`}
              >
                <Icon size={18} aria-hidden />
                <span>{item.label}</span>
              </NavLink>
            );
          })}
        </nav>
      )}

      {children}
      {variant === "wa" && footer}
      <HubLayer />

      <div id="sr-announcer" className="sr-only" role="status" aria-live="polite" />
    </div>
  );
}
