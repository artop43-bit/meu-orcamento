import { useEffect, type MouseEvent, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ChevronRight, Layers, LayoutGrid, LogOut, Monitor, Moon, ShieldCheck, Sun, Wallet } from "lucide-react";
import { Link } from "react-router";

import { authApi, ME_KEY, useMe } from "../api/auth";
import { useProfile } from "../api/profile";
import { Avatar } from "../components/media";
import { Brand, PageHeader } from "../components/ui";
import { announce } from "../lib/announce";
import { nextTheme, originOf, setAppearance, syncAppearance, THEMES } from "../lib/appearance";
import { HUB_SOLUTIONS, type SolutionIcon } from "../lib/hub";
import { prefetchProps } from "../lib/prefetch";
import { usePrefs } from "../lib/prefs";
import { preloadPages } from "./lazy";
import { releaseLabel } from "../release";

const SOLUTION_ICONS: Record<SolutionIcon, ReactNode> = {
  wallet: <Wallet size={20} />,
  layers: <Layers size={20} />,
};

const THEME_ICON = {
  system: <Monitor size={17} />,
  light: <Sun size={17} />,
  dark: <Moon size={17} />,
} as const;

/** Menu anterior às aplicações principais: escolhe qual solução abrir usando a mesma conta. */
export default function Hub() {
  const queryClient = useQueryClient();
  const { data: user } = useMe();
  const profile = useProfile();
  const prefs = usePrefs();

  useEffect(() => {
    document.title = "Hub de Soluções · Meu Orçamento";
  }, []);

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
          <Brand label="Hub de Soluções" icon={<LayoutGrid size={18} />} />
          <div className="hub__actions">
            <Link to="/ajustes/perfil" className="hub__account" title="Ver meu perfil">
              <Avatar fileId={profile.data?.avatar_id} name={displayName} size={28} />
              <span className="hub__account-name">{displayName}</span>
            </Link>
            {user?.is_admin && (
              <Link to="/admin" className="icon-btn" aria-label="Administração" title="Administração">
                <ShieldCheck size={18} />
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
        <PageHeader
          title="Escolha uma solução"
          subtitle="Acesse as aplicações conectadas à sua conta neste servidor."
        />

        <ul className="hub-grid" aria-label="Soluções disponíveis">
          {HUB_SOLUTIONS.map((solution) => (
            <li key={solution.id}>
              {solution.status === "active" && solution.to ? (
                <Link
                  to={solution.to}
                  className="settings-list__item hub-card"
                  {...prefetchProps(queryClient, solution.to)}
                >
                  <span className="settings-list__icon" aria-hidden>
                    {SOLUTION_ICONS[solution.icon]}
                  </span>
                  <span className="settings-list__text">
                    <span className="hub-card__head">
                      <strong>{solution.name}</strong>
                      <span className="badge badge--ok">{solution.badge}</span>
                    </span>
                    <span className="muted small">{solution.description}</span>
                  </span>
                  <span className="hub-card__cta" aria-hidden>
                    <span className="small">{solution.actionLabel}</span>
                    <ChevronRight size={18} />
                  </span>
                </Link>
              ) : (
                <div className="settings-list__item hub-card hub-card--soon" aria-disabled="true">
                  <span className="settings-list__icon hub-card__icon--muted" aria-hidden>
                    {SOLUTION_ICONS[solution.icon]}
                  </span>
                  <span className="settings-list__text">
                    <span className="hub-card__head">
                      <strong>{solution.name}</strong>
                      <span className="badge badge--muted">{solution.badge}</span>
                    </span>
                    <span className="muted small">{solution.description}</span>
                  </span>
                </div>
              )}
            </li>
          ))}
        </ul>
      </main>

      <footer className="footer hub__footer">
        <Link to="/ajustes/preferencias">Preferências</Link>
        <Link to="/privacidade">Privacidade</Link>
        <Link to="/termos">Termos de uso</Link>
        <span className="muted">{releaseLabel()}</span>
      </footer>
      <div id="sr-announcer" className="sr-only" role="status" aria-live="polite" />
    </div>
  );
}
