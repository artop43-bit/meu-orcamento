import {
  createContext,
  Suspense,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Lock } from "lucide-react";
import { Link, Navigate, useLocation, useNavigate } from "react-router";

import { useMe } from "../api/auth";
import { prefersReducedMotion } from "../lib/announce";
import {
  areaForPath,
  canSkipSplashByClick,
  computeSplashExitDelay,
  findSolution,
  isSolutionBlocked,
  leaveStillApplies,
  navigateDelay,
  shouldBlockSolutionJump,
  SOLUTION_LEAVE_MS,
  splashSolutionForAreas,
  splashTiming,
  type HubSolution,
  type SplashTiming,
} from "../lib/hub";
import { prefetchRoute } from "../lib/prefetch";
import { preloadSolutionRoute } from "../pages/lazy";
import { SolutionIcon } from "./SolutionIcon";

/*
 * Transição padrão entre o Hub e as soluções.
 *
 * - Entrada: a animação (logo → nome da solução) fica no nível do App, fora do <Suspense> geral,
 *   então continua na tela enquanto o código da solução é baixado. Ela só sai quando a tela da
 *   solução foi montada de verdade (sinal dentro do <Suspense> da moldura, em SolutionGate).
 * - Bloqueio: de uma solução não se pula direto para outra; a pessoa volta antes ao Hub.
 * - Saída: "Sair" esmaece a solução e só então volta ao Hub (useLeaveSolution).
 * Sem View Transitions do navegador (já usadas na troca de tema): só animações CSS comuns.
 */

const ENTERING_ATTR = "data-solution-entering";
const LEAVING_ATTR = "data-solution-leaving";
/** Se a volta ao Hub não acontecer, a solução reaparece depois deste tempo (rede de segurança). */
const LEAVE_SAFETY_MS = 1500;

type Splash = {
  key: number;
  solution: HubSolution;
  /** Momento (performance.now) em que a animação apareceu. */
  shownAt: number;
  /** Começou no clique de um cartão do Hub (a animação entra esmaecendo por cima do Hub). */
  fromCard: boolean;
  phase: "showing" | "leaving";
  timing: SplashTiming;
};

type PendingNavigation = { key: number; to: string };

type TransitionContext = {
  /** Última área visitada (solução, "hub" ou null), atualizada depois de cada troca de endereço. */
  lastAreaRef: RefObject<string | null>;
  /** Clique num cartão do Hub: mostra a animação, espera o código da tela e então troca de tela. */
  enter: (solution: HubSolution, chunk: Promise<unknown>) => void;
  /** A tela da solução foi montada: a animação pode sair. */
  markReady: (solutionId: string) => void;
};

const SolutionTransitionContext = createContext<TransitionContext | null>(null);

/** Moldura de transição das soluções: fica dentro do <BrowserRouter> e fora do <Suspense> do App. */
export function SolutionTransitionProvider({ children }: { children: ReactNode }) {
  const location = useLocation();
  const navigate = useNavigate();
  const [active, setActive] = useState<Splash | null>(null);
  // Cópias imediatas do estado: os sinais chegam de efeitos de outros componentes no mesmo ciclo.
  const activeRef = useRef<Splash | null>(null);
  const pendingRef = useRef<PendingNavigation | null>(null);
  const lastAreaRef = useRef<string | null>(null);
  /** A pessoa pulou a animação antes de a tela trocar: a chegada não toca a animação de novo. */
  const suppressRef = useRef<string | null>(null);
  const timersRef = useRef<number[]>([]);
  const enteringTimerRef = useRef<number | undefined>(undefined);
  const seqRef = useRef(0);

  const clearTimers = useCallback(() => {
    timersRef.current.forEach((id) => window.clearTimeout(id));
    timersRef.current = [];
  }, []);

  const later = useCallback((fn: () => void, ms: number) => {
    timersRef.current.push(window.setTimeout(fn, Math.max(0, ms)));
  }, []);

  const update = useCallback((next: Splash | null) => {
    activeRef.current = next;
    setActive(next);
  }, []);

  /** Tira a animação da tela na hora (fim da saída, pulo ou troca de endereço). */
  const finish = useCallback(
    (key: number) => {
      if (activeRef.current?.key !== key) return;
      clearTimers();
      pendingRef.current = null;
      update(null);
    },
    [clearTimers, update],
  );

  /** Começa a saída: a animação esmaece e o conteúdo da solução entra por baixo. */
  const beginExit = useCallback(
    (key: number) => {
      const current = activeRef.current;
      if (!current || current.key !== key || current.phase === "leaving") return;
      update({ ...current, phase: "leaving" });
      if (current.timing.contentMs > 0) {
        const root = document.documentElement;
        root.setAttribute(ENTERING_ATTR, current.solution.id);
        window.clearTimeout(enteringTimerRef.current);
        enteringTimerRef.current = window.setTimeout(() => root.removeAttribute(ENTERING_ATTR), current.timing.contentMs);
      }
      later(() => finish(key), current.timing.exitMs);
    },
    [finish, later, update],
  );

  const show = useCallback(
    (solution: HubSolution, fromCard: boolean): Splash => {
      clearTimers();
      pendingRef.current = null;
      const timing = splashTiming(prefersReducedMotion());
      const splash: Splash = {
        key: ++seqRef.current,
        solution,
        shownAt: performance.now(),
        fromCard,
        phase: "showing",
        timing,
      };
      update(splash);
      // Limite: mesmo que a tela demore, a animação não passa de ~2,5 s.
      later(() => beginExit(splash.key), timing.visibleMaxMs);
      return splash;
    },
    [beginExit, clearTimers, later, update],
  );

  const enter = useCallback(
    (solution: HubSolution, chunk: Promise<unknown>) => {
      const to = solution.to;
      // Já há uma entrada na tela (Enter repetido no cartão, duplo clique): não recomeça a animação.
      if (!to || activeRef.current) return;
      const splash = show(solution, true);
      const pending: PendingNavigation = { key: splash.key, to };
      pendingRef.current = pending;
      const go = () => {
        if (pendingRef.current !== pending) return;
        pendingRef.current = null;
        navigate(to);
      };
      later(go, navigateDelay(null, splash.timing));
      void chunk
        .catch(() => undefined)
        .then(() => {
          if (pendingRef.current !== pending) return;
          const readyAfter = performance.now() - splash.shownAt;
          later(go, navigateDelay(readyAfter, splash.timing) - readyAfter);
        });
    },
    [later, navigate, show],
  );

  const markReady = useCallback(
    (solutionId: string) => {
      const current = activeRef.current;
      if (!current || current.solution.id !== solutionId || current.phase !== "showing" || pendingRef.current) return;
      later(() => beginExit(current.key), computeSplashExitDelay(performance.now() - current.shownAt, current.timing));
    },
    [beginExit, later],
  );

  /** Esc ou clique: pula a animação (e, se a troca de tela ainda não aconteceu, troca agora). */
  const skip = useCallback(() => {
    const current = activeRef.current;
    if (!current) return;
    const pending = pendingRef.current;
    // Ainda no Hub (troca de tela pendente ou em andamento): a chegada não repete a animação.
    if (lastAreaRef.current !== current.solution.id) suppressRef.current = current.solution.id;
    finish(current.key);
    if (pending) navigate(pending.to);
  }, [finish, navigate]);

  // Antes de pintar a nova tela: decide a animação e guarda a área visitada (usada pelo bloqueio).
  useLayoutEffect(() => {
    const prevArea = lastAreaRef.current;
    const nextArea = areaForPath(location.pathname);
    lastAreaRef.current = nextArea;
    const suppressed = suppressRef.current;
    suppressRef.current = null;
    // O endereço mudou: a troca de tela pedida pelo cartão já aconteceu ou perdeu o sentido
    // (voltar do navegador durante a animação). Não navega de novo depois.
    pendingRef.current = null;
    // A solução que estava saindo já foi trocada pela nova tela.
    document.documentElement.removeAttribute(LEAVING_ATTR);

    const current = activeRef.current;
    if (current && current.solution.id !== nextArea) finish(current.key);

    const target = splashSolutionForAreas(prevArea, nextArea);
    if (target && target.id !== suppressed && activeRef.current?.solution.id !== target.id) show(target, false);
  }, [location.pathname]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!active) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") skip();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active?.key, skip]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(
    () => () => {
      clearTimers();
      window.clearTimeout(enteringTimerRef.current);
      // Nada de atributo esquecido em <html> (ele esconderia a moldura da próxima solução).
      document.documentElement.removeAttribute(ENTERING_ATTR);
      document.documentElement.removeAttribute(LEAVING_ATTR);
    },
    [clearTimers],
  );

  const value = useMemo<TransitionContext>(() => ({ lastAreaRef, enter, markReady }), [enter, markReady]);

  return (
    <SolutionTransitionContext.Provider value={value}>
      {children}
      {active && (
        <div
          key={active.key}
          className={[
            "solution-splash",
            active.fromCard ? "solution-splash--from-hub" : "",
            active.phase === "leaving" ? "is-leaving" : "",
          ]
            .filter(Boolean)
            .join(" ")}
          data-solution-transition={active.solution.id}
          role="status"
          aria-live="polite"
          aria-label={`Abrindo ${active.solution.name}`}
          onClick={(event) => {
            if (canSkipSplashByClick(performance.now() - active.shownAt, event.detail)) skip();
          }}
        >
          <div className="solution-splash__stage">
            <div className="solution-splash__emblem" aria-hidden>
              <span className="solution-splash__ring" />
              <span className="solution-splash__logo">
                <SolutionIcon icon={active.solution.icon} size={34} />
              </span>
            </div>
            <div className="solution-splash__title-wrap">
              <span className="solution-splash__name">{active.solution.name}</span>
              <span className="solution-splash__bar" aria-hidden />
            </div>
          </div>
        </div>
      )}
    </SolutionTransitionContext.Provider>
  );
}

/**
 * Cartões do Hub: abre a solução com a animação padrão. Já começa a baixar o código e os dados
 * da primeira tela; a troca de tela acontece quando estiverem prontos (com mínimo e limite).
 */
export function useEnterSolution(): (solution: HubSolution) => void {
  const context = useContext(SolutionTransitionContext);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  return useCallback(
    (solution: HubSolution) => {
      const to = solution.to;
      if (!to) return;
      prefetchRoute(queryClient, to);
      const chunk = preloadSolutionRoute(to);
      if (context) context.enter(solution, chunk);
      else navigate(to);
    },
    [context, navigate, queryClient],
  );
}

/**
 * "Sair" de dentro de uma solução: volta ao Hub de Soluções (sem deslogar a conta).
 * Contrato usado pelas molduras das soluções (Shell e MessagingShell): () => void.
 * A solução esmaece rapidamente antes da troca; com "reduzir movimento", volta na hora.
 */
export function useLeaveSolution(): () => void {
  const navigate = useNavigate();
  const leavingRef = useRef(false);
  return useCallback(() => {
    if (leavingRef.current) return;
    if (prefersReducedMotion()) {
      navigate("/");
      return;
    }
    leavingRef.current = true;
    const root = document.documentElement;
    const token = String(Date.now());
    const from = window.location.pathname;
    // Uma entrada ainda animando não briga com a saída.
    root.removeAttribute(ENTERING_ATTR);
    root.setAttribute(LEAVING_ATTR, token);
    window.setTimeout(() => {
      leavingRef.current = false;
      // A pessoa já foi para outra área durante o esmaecimento: não puxa de volta para o Hub.
      if (!leaveStillApplies(from, window.location.pathname)) {
        if (root.getAttribute(LEAVING_ATTR) === token) root.removeAttribute(LEAVING_ATTR);
        return;
      }
      navigate("/");
      window.setTimeout(() => {
        if (root.getAttribute(LEAVING_ATTR) === token) root.removeAttribute(LEAVING_ATTR);
      }, LEAVE_SAFETY_MS);
    }, SOLUTION_LEAVE_MS);
  }, [navigate]);
}

/** Avisa a transição quando a tela da solução terminou de montar (fica dentro do <Suspense>). */
function SolutionReady({ solution }: { solution: string }) {
  const context = useContext(SolutionTransitionContext);
  useEffect(() => {
    context?.markReady(solution);
  }, [context, solution]);
  return null;
}

/**
 * Envolve a moldura de cada solução (Shell, MessagingShell) nas rotas do App:
 * - barra o salto direto de outra solução (por link interno ou voltar/avançar): volta ao Hub
 *   antes de a nova solução aparecer. Endereço digitado, favorito e notificação abrem direto;
 * - avisa a animação de entrada quando a tela foi montada de verdade.
 */
export function SolutionGate({
  solution,
  children,
  fallback = null,
}: {
  solution: string;
  children: ReactNode;
  fallback?: ReactNode;
}) {
  const context = useContext(SolutionTransitionContext);
  const { data: user } = useMe();
  const solutionBlocked = isSolutionBlocked(solution, user?.blocked_resources);
  // Decidido ao entrar na solução, comparando com a área visitada antes desta troca de endereço.
  // O React Router reaproveita a mesma instância entre rotas irmãs (de uma solução para a outra),
  // então a decisão guarda a solução e é refeita quando ela muda.
  const [decision, setDecision] = useState(() => ({
    solution,
    blocked: shouldBlockSolutionJump(context?.lastAreaRef.current ?? null, solution),
  }));
  let blocked = decision.blocked;
  if (decision.solution !== solution) {
    blocked = shouldBlockSolutionJump(context?.lastAreaRef.current ?? null, solution);
    setDecision({ solution, blocked });
  }
  if (blocked) return <Navigate to="/" replace />;
  if (solutionBlocked) {
    const meta = findSolution(solution);
    return (
      <main className="hub__main" style={{ paddingTop: 48 }}>
        <section className="card stack" style={{ maxWidth: 520, margin: "0 auto", alignItems: "flex-start" }}>
          <span className="settings-list__icon" aria-hidden>
            <Lock size={20} />
          </span>
          <h1 style={{ margin: 0, fontSize: "1.3rem" }}>Acesso bloqueado pelo administrador</h1>
          <p className="muted" style={{ margin: 0 }}>
            O acesso à solução <strong>{meta?.name ?? solution}</strong> foi bloqueado para a sua conta pelo administrador da plataforma.
          </p>
          <Link to="/" className="btn btn--primary">
            Voltar ao Hub
          </Link>
        </section>
      </main>
    );
  }
  return (
    <Suspense fallback={fallback}>
      {children}
      <SolutionReady solution={solution} />
    </Suspense>
  );
}
